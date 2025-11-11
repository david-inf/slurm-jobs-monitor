"""Sandbox for testing the AI Agent"""

from slurmonitor.agent import LogSummarizerAgent

from pathlib import Path
from rich.console import Console

console = Console()


def test_agent_summarization():
    """
    Test the LogSummarizerAgent summarization functionality alone.

    We have a full log file from a Slurm job. The idea is to stream
    this log to the agent and get a summary simulating a real use case.
    """
    console.print("\n[bold blue]Testing LogSummarizerAgent Summarization[/bold blue]")
    log_path: Path = Path("tests/2392_exp1_0.out")
    if not log_path.is_file():
        console.print(f"Test log file '{log_path}' not found. Skipping test.")
        return
    console.print(f"✓ Loaded test log file: {log_path}")

    ckpt = "google/flan-t5-base"
    # ckpt = "facebook/bart-large-cnn"
    # ckpt = "Qwen/Qwen3-4B-Instruct-2507"
    agent = LogSummarizerAgent(
        model_name=ckpt,
        device="cpu",
        use_quantization=False,
        use_causal_model=True
    )
    console.print("✓ Initialized LogSummarizerAgent")
    summary = agent.summarize(log_path, verbose=True)
    console.print("\n[bold green]Generated Summary:[/bold green]")
    console.print(summary)


if __name__ == "__main__":
    test_agent_summarization()
