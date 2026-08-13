from cloud_worker import process_reading, logger


if __name__ == "__main__":
    logger.info("Running one-shot Shelly Cloud -> Supabase ingestion")
    process_reading()