"""
Schedule Storage Service

Persists heating schedule to Supabase so the frontend can display
scheduled heating slots on the chart.

Table schema (needs to be created in Supabase):
CREATE TABLE heating_schedule (
    id SERIAL PRIMARY KEY,
    slot_start TIMESTAMPTZ NOT NULL,
    slot_end TIMESTAMPTZ NOT NULL,
    price DECIMAL(10, 4) NOT NULL,
    heater_type VARCHAR(20) NOT NULL,  -- 'off_peak' or 'peak'
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(slot_start, heater_type)
);

-- Index for efficient queries
CREATE INDEX idx_schedule_slot_start ON heating_schedule(slot_start);
CREATE INDEX idx_schedule_heater_type ON heating_schedule(heater_type);
"""

import os
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ScheduleStorage:
    """
    Stores and retrieves heating schedule from Supabase.
    """

    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")

        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase configuration missing. Schedule storage disabled.")
            self.enabled = False
        else:
            self.enabled = True
            self.headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            }

    def save_schedule(self, slots, heater_type="off_peak"):
        """
        Saves heating schedule to Supabase.
        Clears old schedule for the heater type and inserts new slots.

        Args:
            slots: List of rate slot dicts with 'valid_from', 'valid_to', 'value_inc_vat'
            heater_type: 'off_peak' or 'peak'
        """
        if not self.enabled:
            logger.debug("Schedule storage disabled, skipping save.")
            return False

        if not slots:
            logger.info(f"No slots to save for {heater_type}")
            return True

        try:
            # First, delete existing future schedule for this heater type
            # Use strftime to ensure proper ISO format with 'T' separator
            now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            delete_url = f"{self.supabase_url}/rest/v1/heating_schedule"
            delete_params = f"heater_type=eq.{heater_type}&slot_start=gte.{now}"

            delete_response = requests.delete(
                f"{delete_url}?{delete_params}",
                headers=self.headers
            )

            if delete_response.status_code not in [200, 204]:
                logger.warning(f"Failed to clear old schedule: {delete_response.status_code} - {delete_response.text}")

            # Insert new schedule
            rows = []
            for slot in slots:
                # Handle both datetime objects and ISO strings
                slot_start = slot['valid_from']
                slot_end = slot['valid_to']

                if hasattr(slot_start, 'isoformat'):
                    slot_start = slot_start.isoformat()
                if hasattr(slot_end, 'isoformat'):
                    slot_end = slot_end.isoformat()

                rows.append({
                    "slot_start": slot_start,
                    "slot_end": slot_end,
                    "price": slot['value_inc_vat'],
                    "heater_type": heater_type,
                    "computed_at": datetime.now(timezone.utc).isoformat()
                })

            insert_url = f"{self.supabase_url}/rest/v1/heating_schedule"
            response = requests.post(
                insert_url,
                json=rows,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"}
            )

            if response.status_code in [200, 201]:
                logger.info(f"Saved {len(rows)} schedule slots for {heater_type} to Supabase")
                return True
            else:
                logger.error(f"Failed to save schedule: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error saving schedule to Supabase: {e}")
            return False

    def get_schedule(self, heater_type=None, from_time=None, to_time=None):
        """
        Retrieves heating schedule from Supabase.

        Args:
            heater_type: Optional filter for 'off_peak' or 'peak'
            from_time: Optional start time filter (datetime or ISO string)
            to_time: Optional end time filter (datetime or ISO string)

        Returns:
            List of schedule slots or empty list on error
        """
        if not self.enabled:
            return []

        try:
            url = f"{self.supabase_url}/rest/v1/heating_schedule"
            params = ["select=*"]

            if heater_type:
                params.append(f"heater_type=eq.{heater_type}")

            if from_time:
                if hasattr(from_time, 'isoformat'):
                    from_time = from_time.isoformat()
                params.append(f"slot_start=gte.{from_time}")

            if to_time:
                if hasattr(to_time, 'isoformat'):
                    to_time = to_time.isoformat()
                params.append(f"slot_end=lte.{to_time}")

            params.append("order=slot_start.asc")

            query_string = "&".join(params)
            response = requests.get(
                f"{url}?{query_string}",
                headers=self.headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to fetch schedule: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error fetching schedule from Supabase: {e}")
            return []
