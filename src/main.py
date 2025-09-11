import uvicorn
import logging

# --- Centralized Logging Configuration ---
# This is the key change. We configure the root logger right at the start.
# Now, any logger created in any other file will inherit this configuration.

# -----------------------------------------

if __name__ == "__main__":
    """
    This is the main entry point for running the application.
    It starts the Uvicorn server, which in turn runs the FastAPI app 
    defined in `src.ingress.api`.
    
    The FastAPI app itself is responsible for starting the background workers
    via its startup event.
    """
    logging.info("Starting Hetairoi server...")
    uvicorn.run(
        "src.ingress.api:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True
    )
