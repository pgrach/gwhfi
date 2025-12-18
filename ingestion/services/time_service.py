import ntplib
import logging
from datetime import datetime, timezone
import pytz
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TimeService:
    def __init__(self, timezone_str='Europe/London'):
        self.timezone = pytz.timezone(timezone_str)
        # Fallback list of reliable NTP servers
        self.ntp_servers = ['pool.ntp.org', 'time.google.com', 'time.windows.com']
        self.offset = 0
        self.last_check = 0

    def now(self):
        """Returns current UTC time (aware)"""
        return datetime.now(timezone.utc)

    def get_local_time(self):
        """Returns current time in local timezone"""
        return self.now().astimezone(self.timezone)

    def check_system_clock(self):
        """
        Checks system clock against multiple NTP servers.
        Returns (offset, is_safe)
        """
        client = ntplib.NTPClient()
        
        for server in self.ntp_servers:
            try:
                logger.info(f"Checking time against {server}...")
                response = client.request(server, version=3, timeout=5)
                self.offset = response.offset
                self.last_check = time.time()
                
                logger.info(f"NTP Time Check ({server}): Offset is {self.offset:.4f} seconds.")
                
                if abs(self.offset) > 5.0:
                    logger.warning(f"CRITICAL: System clock is off by {self.offset} seconds!")
                    return self.offset, False
                    
                # If we get here, check passed
                return self.offset, True
                
            except Exception as e:
                logger.warning(f"Failed to check NTP time from {server}: {e}")
                continue # Try next server
        
        logger.error("All NTP servers failed to respond.")
        return None, False

if __name__ == "__main__":
    ts = TimeService()
    print("Checking System Clock...")
    offset, safe = ts.check_system_clock()
    print(f"Offset: {offset}, Safe: {safe}")
    
    print(f"UTC Now: {ts.now()}")
    print(f"Local Now: {ts.get_local_time()}")
