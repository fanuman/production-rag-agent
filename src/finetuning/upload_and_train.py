"""
Fine-tuning upload + job creation for the "no good match" response pattern.

RUNNING THIS FILE:
    python -m src.finetuning.upload_and_train

This uploads the training file (free - no cost for the upload step itself)
and prints the resulting file ID. It deliberately STOPS there.

Actually submitting the fine-tuning job costs real money (charged per
training token x number of epochs), and the resulting fine-tuned model
costs more per token at inference than the base model, ongoing. To
actually train:
  1. Confirm current pricing at platform.openai.com/account/billing/overview
  2. Uncomment the `create_job()` call at the bottom of this file
  3. Re-run this file
This is a deliberate, one-line decision point - not something to run
by accident.
"""

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

client = OpenAI()

DATASET_PATH = "src/finetuning/datasets/no_match_pattern.jsonl"
BASE_MODEL = "gpt-4o-mini-2024-07-18"


def upload_file():
    with open(DATASET_PATH, "rb") as f:
        file = client.files.create(file=f, purpose="fine-tune")
    print(f"Uploaded file: {file.id} ({file.bytes} bytes)")
    return file.id


def create_job(file_id):
    job = client.fine_tuning.jobs.create(training_file=file_id, model=BASE_MODEL)
    print(f"Fine-tuning job created: {job.id} (status: {job.status})")
    return job


def check_status(job_id):
    job = client.fine_tuning.jobs.retrieve(job_id)
    print(f"Status: {job.status}")
    if job.status == "succeeded":
        print(f"Fine-tuned model: {job.fine_tuned_model}")
    return job


if __name__ == "__main__":
    file_id = upload_file()

    # Deliberately not run today - uncomment when ready to spend real money:
    # job = create_job(file_id)