"""AI Agent for summarizing log files from Slurm jobs."""

import time
from pathlib import Path
from typing import List
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
# from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LogSummarizerAgent:
    """Agent that summarizes log files from Slurm jobs."""

    def __init__(
        self,
        model_name: str = "google/flan-t5-small",
        device: str = "cpu",
        use_quantization: bool = True,
        max_input_length: int = 1024,
        max_output_length: int = 256,
        # use_causal_model: bool = False,  # default use a seq2seq model
    ) -> None:
        """
        Initialize the LogSummarizerAgent.

        Args:
            model_name: HuggingFace model identifier. Options:
                - "google/flan-t5-base" (default, 250M params, ~1GB)
                - "google/flan-t5-small" (80M params, lighter)
                - "facebook/bart-base" (140M params, good for summaries)
            device: "cpu" or "cuda"
            use_quantization: Enable int8 quantization to reduce memory (default: True)
            max_input_length: Maximum tokens for input
            max_output_length: Maximum tokens for output summary
        """
        self.device = device
        self.model_name = model_name
        self.max_input_length = max_input_length
        self.max_output_length = max_output_length
        self.use_quantization = use_quantization

        # Performance metrics
        self.metrics = {
            'total_summaries': 0,
            'total_time': 0.0,
            'preprocessing_time': 0.0,
            'inference_time': 0.0,
            'avg_time_per_summary': 0.0
        }

        logger.info(f"Loading model: {model_name}")
        load_start = time.time()

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        # Load model with optimizations
        if use_quantization and device == "cpu":
            # Prefer Hugging Face / bitsandbytes 8-bit loading on CPU.
            # This requires `bitsandbytes` (bnb) and a compatible `transformers`.
            logger.info("Attempting to load model with 8-bit quantization (bitsandbytes)...")
            try:
                # load_in_8bit places 8-bit params on the requested device via device_map.
                # Use an explicit cpu device map to avoid device auto-placement.
                self.model = AutoModelForSeq2SeqLM.from_pretrained(
                    model_name,
                    load_in_8bit=True,
                    device_map={"": "cpu"},
                )
            except Exception as e:
                # If bitsandbytes or compatible transformers aren't available, fall back.
                logger.warning(
                    "Failed to load 8-bit quantized model with bitsandbytes: %s. Falling back to float32.",
                    e,
                )
                self.model = AutoModelForSeq2SeqLM.from_pretrained(
                    model_name,
                    dtype=torch.float32,
                )
        else:
            # Standard loading
            dtype = torch.float16 if device == "cuda" else torch.float32
            logger.info(f"Loading model with dtype: {dtype}")
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                model_name,
                dtype=dtype
            )

        self.model = self.model.to(device)
        self.model.eval()
        logger.info(f"Model loaded in {time.time() - load_start:.2f}s")
        self._memory_footprint()

    def _preprocess_log(self, log_path: Path) -> str:
        """Read and preprocess log file content."""
        with open(log_path, "r", encoding="utf-8", errors="ignore") as file:
            log_content = file.read()
        # Additional preprocessing can be added here if needed
        return log_content

    def _prompt_template(self, log_content: str) -> str:
        """Create a prompt for the model based on log content."""
        prompt = (
            "Describe in few sentences the following log file content. "
            "This is a partial log file of a GPT pretraining.\n\n"
            # "Focus on key events, errors, and overall job status.\n\n"
            f"{log_content}\n\n"
            "Summary:"
        )
        return prompt

    def summarize(self, log_path: Path, verbose: bool = False) -> str:
        """
        Summarize the provided log content.

        Args:
            log_path: Where to find the log file to summarize.
            verbose: Whether to log detailed information.

        Returns:
            A summary string of the log content.
        """
        # (1) Preprocess log file
        preprocess_start = time.time()
        log_content = self._preprocess_log(log_path)
        self.metrics['preprocessing_time'] = time.time() - preprocess_start

        # (2) Create prompt for the model
        prompt = self._prompt_template(log_content)
        # (3) Tokenize input
        inputs = self.tokenizer(
            prompt,
            max_length=self.max_input_length,
            truncation=True,
            return_tensors="pt",
        ).to(self.device)

        # (4) Generate summary
        inference_start = time.time()
        if verbose:
            logger.info(f"Generating summary for: {log_path.name}")
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=self.max_output_length,
                num_beams=4,
                early_stopping=True,
                no_repeat_ngram_size=3,
            )
        self.metrics['inference_time'] = time.time() - inference_start
        summary = self.tokenizer.decode(
            outputs[0],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True
        )

        # Update metrics
        self.metrics['total_summaries'] += 1
        self.metrics['total_time'] += time.time() - preprocess_start
        self.metrics['avg_time_per_summary'] = (
            self.metrics['total_time'] / self.metrics['total_summaries']
        )

        if verbose:
            logger.info(f"Metrics: {self.metrics}")
        return summary

    def _memory_footprint(self) -> float:
        """Estimate the memory footprint of the model in MB."""
        n_params = sum(p.numel() for p in self.model.parameters())

        params_sizes = {"int8": 1, "float16": 2, "float32": 4}
        param_size = None
        if self.use_quantization and self.device == "cpu":
            param_type = "int8"
            param_size = params_sizes[param_type]
        elif self.device == "cuda":
            param_type = "float16"
            param_size = params_sizes[param_type]
        else:
            param_type = "float32"
            param_size = params_sizes[param_type]
        param_size_mb = (n_params * param_size) / (1024 ** 2)

        logger.info(f"Model parameters: {n_params:,} ({n_params/1e6:.2f} M)")
        logger.info(f"Estimated memory footprint ({param_type}): ~{param_size_mb:.2f} MB")
        # Add overhead
        total_estimate_mb = param_size_mb * 1.2
        logger.info(f"Total estimated memory footprint: ~{total_estimate_mb:.1f} MB")


class SimpleLogSummarizer:
    """Simple pipeline that summarizes a log file"""

    def __init__(self):
        pass

    def summarize(self, log_path: Path, verbose: bool = False) -> str:
        """Simple text summarization pipeline"""
        with open(log_path, 'r', encoding='utf-8') as f:
            # Return a list containing each line in the file
            content: List[str] = f.readlines()

        # Take few lines from the file
        summary: List[str] = content[-5:]
        # Format the summary
        summary = "".join(summary)

        return summary
