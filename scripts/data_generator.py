import json
import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# Add project root and src directory to sys.path
project_root = str(Path(__file__).resolve().parent.parent)
src_dir = str(Path(project_root) / "src")

load_dotenv(Path(project_root) / ".env")

if project_root not in sys.path:
    sys.path.append(project_root)
if src_dir not in sys.path:
    sys.path.append(src_dir)

from pydantic import BaseModel, Field
from src.infrastructure.db.s3_client import S3Client
from src.infrastructure.llm.llm_provider import get_chat_llm
from src.infrastructure.config import NOTEBOOKS_DIR

from pydantic import BaseModel, Field

class DistilledIncidentSchema(BaseModel):
    """
    Schema for capturing structural fields from logs, transcripts, or runbooks
    to ensure seamless ingestion into Qdrant procedural memory.
    """
    problem: str = Field(
        description="The core technical issue or alert reported in the transcript/runbook."
    )
    root_cause: str = Field(
        description="The underlying technical reason or configuration failure that caused the problem."
    )
    resolution: str = Field(
        description="The exact step-by-step technical fix, terminal commands, or mitigation steps applied to resolve the issue."
    )
    tier: int = Field(
        description=(
            "The operational support tier classification matching the 4 incident types exactly: "
            "1 = Access & Identity (VPN issues, password resets, access requests, FAQs), "
            "2 = Resource Provisioning (creating/configuring instances, databases, infrastructure deployment), "
            "3 = Performance Degradation (slow response times, database query performance, high latency logs), "
            "4 = Critical Outages (server crashes, severe memory leaks, core services down, system completely unavailable)."
        )
    )
    source_file: str = Field(
        description="Name of the source file where data was stored"
    )

def generate_distilled_data_s3():
    logger.info("Initializing S3 Client...")
    s3_client = S3Client()
    
    logger.info("Loading JSON objects from S3...")
    data_list = s3_client.load_json_objects()
    logger.info(f"Loaded {len(data_list)} objects from S3.")
    
    logger.info("Initializing LLM with structured output...")
    # Initialize the LLM with structured output matching our schema
    llm = get_chat_llm(temperature=0).with_structured_output(DistilledIncidentSchema)
    
    results = []
    
    for data in data_list:
        source_file = data.get('source_file', 'unknown_file')
        logger.info(f"Processing source file: {source_file}")
        
        prompt = f"Extract the required information from the following transcript/data:\n\n{json.dumps(data, indent=2)}"
        try:
            # Process with LLM
            extracted = llm.invoke(prompt)
            # Add to results
            results.append(extracted.model_dump())
            logger.success(f"Successfully processed {source_file}")
        except Exception as e:
            logger.error(f"Error processing {source_file}: {e}")

    # Save to data folder
    os.makedirs("data", exist_ok=True)
    output_file = "data/distilled_incidents.json"
    logger.info(f"Saving extracted data to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    logger.success(f"Saved {len(results)} records to {output_file}")

# markdown files from data/notebooks
def generate_distilled_data_local():
    # loading makrdown files from notebooks folder
    # get files from NOTEBOOKS_DIR
    files = list(NOTEBOOKS_DIR.glob("*.md"))
    logger.info(f"Found {len(files)} markdown files.")

    # Initialize the LLM with structured output matching our schema
    llm = get_chat_llm(temperature=0).with_structured_output(DistilledIncidentSchema)

    # read each file and extract the required information
    results = []
    for file in files:
        with open(file, "r", encoding="utf-8") as f:
            data = f.read()
            logger.info(f"Processing file: {file.name}")
            
            # Since data is a string (markdown), we don't need json.dumps
            # We also pass the file name in the prompt to help extraction
            prompt = f"Extract the required information from the following transcript/data. The source file name is '{file.name}':\n\n{data}"
            try:
                # Process with LLM
                extracted = llm.invoke(prompt)
                
                # Convert to dict and explicitly set the source file name to guarantee correctness
                extracted_dict = extracted.model_dump()
                extracted_dict["source_file"] = file.name
                
                # Add to results
                results.append(extracted_dict)
                logger.success(f"Successfully processed {file.name}")
            except Exception as e:
                logger.error(f"Error processing {file.name}: {e}")

    # Save to data folder
    os.makedirs("data", exist_ok=True)
    output_file = "data/distilled_incidents_local.json"
    logger.info(f"Saving extracted data to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    logger.success(f"Saved {len(results)} records to {output_file}")

if __name__ == "__main__":
    # You can change this to generate_distilled_data_local() to run the local one
    generate_distilled_data_local()