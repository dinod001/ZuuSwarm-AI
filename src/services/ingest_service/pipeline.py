import json
import os
import sys

# Add the project root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from loguru import logger

from src.services.ingest_service.s3_ingesting import ingest_transcripts_to_s3
from scripts.data_generator import generate_distilled_data_s3, generate_distilled_data_local
from src.services.ingest_service.chunking import custom_chunking
from src.infrastructure.llm.embeddings import get_default_embeddings
from src.infrastructure.db.qdrant_client import upsert_chunks, upsert_cag_chunks

def run_pipeline():
    logger.info("🚀 ===========================================================================")
    logger.info("🌟 INITIATING ZUUSWARM AI DATA INGESTION PIPELINE 🌟")
    logger.info("🚀 ===========================================================================")
    
    # 1. Upload raw data to S3 first
    logger.info("☁️  [STEP 1/6] Uploading raw transcripts to S3...")
    s3_upload_status = ingest_transcripts_to_s3()
    if s3_upload_status:
        logger.success("✅ Raw transcripts successfully uploaded to S3!")
    else:
        logger.warning("⚠️  S3 upload skipped or returned False. Continuing with existing S3 data...")

    # 2. Fetch data from S3 and local notebooks
    logger.info("📥 [STEP 2/6] Fetching raw incident data from S3 and Local Notebooks...")
    s3_data = generate_distilled_data_s3()
    local_data = generate_distilled_data_local()
    
    # Combine data
    all_incidents = s3_data + local_data
    logger.success(f"📦 Successfully collected a total of {len(all_incidents)} incidents!")
    
    # Save full list locally
    os.makedirs("data", exist_ok=True)
    full_output_file = "data/all_distilled_incidents.json"
    logger.info(f"💾 Saving complete dataset locally to '{full_output_file}'...")
    with open(full_output_file, "w", encoding="utf-8") as f:
        json.dump(all_incidents, f, indent=4, ensure_ascii=False)
        
    # 3. Chunk data
    logger.info("✂️  [STEP 3/6] Formatting and chunking data for embedding...")
    chunks, texts_to_embed = custom_chunking(all_incidents)
    logger.success(f"🧩 Successfully created {len(texts_to_embed)} chunks.")
    
    # 4. Generate embeddings
    logger.info("🧠 [STEP 4/6] Generating dense vector embeddings (this might take a moment)...")
    embedder = get_default_embeddings(show_progress=True)
    embeddings = embedder.embed_documents(texts_to_embed)
    logger.success("⚡ Embeddings generated successfully!")
    
    # 5. Upsert to Qdrant (Main Collection)
    logger.info("🗄️  [STEP 5/6] Upserting all chunks into the main Qdrant vector database...")
    upsert_chunks(chunks, embeddings)
    
    # 6. Filter Tier 1 incidents and upsert to CAG Collection
    logger.info("🔍 [STEP 6/6] Filtering high-priority (Tier 1) incidents for CAG Cache...")
    tier_1_chunks = []
    tier_1_embeddings = []
    for i, chunk in enumerate(chunks):
        if chunk.get("tier") == 1:
            tier_1_chunks.append(chunk)
            tier_1_embeddings.append(embeddings[i])
            
    if tier_1_chunks:
        logger.info(f"🛡️  Upserting {len(tier_1_chunks)} Tier 1 chunk(s) to the specialized CAG Collection...")
        upsert_cag_chunks(tier_1_chunks, tier_1_embeddings)
        logger.success("✅ CAG Cache populated successfully.")
    else:
        logger.warning("⚠️  No Tier 1 chunks were found. CAG collection update skipped.")
        
    logger.info("🚀 ===========================================================================")
    logger.success("🎉 ZUUSWARM AI INGESTION PIPELINE COMPLETED SUCCESSFULLY! 🎉")
    logger.info("🚀 ===========================================================================")

if __name__ == "__main__":
    run_pipeline()
