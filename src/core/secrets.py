import boto3
import json
import os

import logging
logger = logging.getLogger(__name__)

def load_secret_into_env(secret_id="production-rag-agent/openai-api-key", region="eu-north-1"):
    try:
        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_id)
        secret_dict = json.loads(response["SecretString"])
        os.environ["OPENAI_API_KEY"] = secret_dict["OPENAI_API_KEY"]
    except Exception as error:
        logger.warning(f"Could not load secret from Secrets Manager, falling back to existing env: {error}")