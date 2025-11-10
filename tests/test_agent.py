"""Sandbox for testing the AI Agent"""

def test_agent_summarization():
    from src.slurmonitor.agent import LogSummarizerAgent

    agent = LogSummarizerAgent(model_name="google/flan-t5-small", device="cpu")
    sample_log = (
        "Job started at 2024-01-01 12:00:00\n"
        "Loading data...\n"
        "Data loaded successfully.\n"
        "Training model...\n"
        "Epoch 1/10 - Loss: 0.8\n"
        "Epoch 2/10 - Loss: 0.6\n"
        "Model training completed.\n"
        "Job finished at 2024-01-01 12:30:00\n"
    )

    summary = agent.summarize(sample_log)
    assert isinstance(summary, str)
    assert "Job started" in summary
    assert "Job finished" in summary
