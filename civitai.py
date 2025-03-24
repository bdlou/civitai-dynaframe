import requests
import time
import random
import schedule
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("civitai_fetcher.log"),
        logging.StreamHandler()
    ]
)

# Configuration variables
CIVITAI_API_URL = "https://civitai.com/api/v1/images"
YOUR_REST_ENDPOINT = "http://localhost:5000/api/PlayFileAPI/PlayImageUrl?"  # Replace with your endpoint
FETCH_INTERVAL_MINUTES = 1
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

class CivitAIImageFetcher:
    def __init__(self, civitai_api_url, rest_endpoint, nsfw_filter=True):
        """
        Initialize the image fetcher.
        
        Args:
            civitai_api_url (str): CivitAI API URL for images
            rest_endpoint (str): Your REST endpoint to send the image URLs to
            nsfw_filter (bool): Whether to filter out NSFW images
        """
        self.civitai_api_url = civitai_api_url
        self.rest_endpoint = rest_endpoint
        self.nsfw_filter = nsfw_filter
        self.current_cursor = None
        self.processed_urls = set()  # Keep track of processed URLs to avoid duplicates
        self.batch_size = 20  # Number of images to fetch per API call
        
    def fetch_images_batch(self):
        """Fetch a batch of images from CivitAI using cursor-based pagination"""
        params = {
            'limit': self.batch_size,
            'sort': 'Most Reactions',
            'period': 'Day',
            'nsfw': not self.nsfw_filter
        }
        
        # Add cursor if we have one
        if self.current_cursor:
            params['cursor'] = self.current_cursor
            logging.info(f"Using cursor: {self.current_cursor}")
        else:
            logging.info("Starting from the beginning (no cursor)")
        
        for _ in range(MAX_RETRIES):
            try:
                response = requests.get(self.civitai_api_url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                # Extract next cursor from metadata if available
                if 'metadata' in data and 'nextCursor' in data['metadata']:
                    self.current_cursor = data['metadata']['nextCursor']
                    logging.info(f"Next cursor: {self.current_cursor}")
                else:
                    # If no next cursor, we've reached the end - reset
                    logging.info("No next cursor found, resetting to beginning")
                    self.current_cursor = None
                
                if 'items' in data and len(data['items']) > 0:
                    # Return all image URLs from this batch
                    image_urls = []
                    for item in data['items']:
                        url = item.get('url')
                        if url and url not in self.processed_urls:
                            image_urls.append(url)
                    
                    if image_urls:
                        logging.info(f"Found {len(image_urls)} new images in this batch")
                        return image_urls
                    else:
                        logging.warning("No new images found in this batch")
                else:
                    logging.warning("No images found in the API response")
                    self.current_cursor = None  # Reset cursor
                
                # If we reach here with an empty list, we'll return an empty list
                return []
                
            except requests.exceptions.RequestException as e:
                logging.error(f"Error fetching images from CivitAI: {e}")
                time.sleep(RETRY_DELAY)
        
        logging.error(f"Failed to fetch images after {MAX_RETRIES} retries")
        return []
    
    def send_to_endpoint(self, image_url):
        """Send the image URL to your REST endpoint"""
        params = {'URL': image_url}
        
        for _ in range(MAX_RETRIES):
            try:
                response = requests.get(self.rest_endpoint, params=params)
                response.raise_for_status()
                logging.info(f"Successfully sent image URL to endpoint: {image_url}")
                # Add to processed URLs after successful send
                self.processed_urls.add(image_url)
                return True
            except requests.exceptions.RequestException as e:
                logging.error(f"Error sending image URL to endpoint: {e}")
                time.sleep(RETRY_DELAY)
        
        logging.error(f"Failed to send image URL to endpoint after {MAX_RETRIES} retries")
        return False
    
    def process(self):
        """Process a batch of images"""
        logging.info("Starting image fetch and send process")
        
        # Periodically clear processed URLs to prevent memory issues
        if len(self.processed_urls) > 1000:
            logging.info("Clearing processed URLs cache")
            self.processed_urls.clear()
        
        # Fetch a batch of images
        image_urls = self.fetch_images_batch()
        
        if not image_urls:
            logging.warning("No images found to process")
            # If no images and we're already at the beginning (no cursor), just wait for next run
            if not self.current_cursor:
                logging.info("No more images available, waiting until next scheduled run")
            return
        
        # Process one random image from the batch
        image_url = random.choice(image_urls)
        logging.info(f"Selected image for processing: {image_url}")
        
        success = self.send_to_endpoint(image_url)
        if success:
            logging.info("Process completed successfully")
        else:
            logging.error("Process failed at the send step")

def main():
    # Create the fetcher
    fetcher = CivitAIImageFetcher(
        civitai_api_url=CIVITAI_API_URL,
        rest_endpoint=YOUR_REST_ENDPOINT
    )
    
    # Schedule the task to run every minute
    schedule.every(FETCH_INTERVAL_MINUTES).minutes.do(fetcher.process)
    
    logging.info(f"Script started. Will fetch images every {FETCH_INTERVAL_MINUTES} minute(s)")
    logging.info(f"REST endpoint: {YOUR_REST_ENDPOINT}")
    
    # Run once immediately
    fetcher.process()
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Script stopped by user")
    except Exception as e:
        logging.critical(f"Unexpected error: {e}")
