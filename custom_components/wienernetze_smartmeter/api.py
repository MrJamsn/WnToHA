"""Minimal Wiener Netze Smart Meter API client - no external dependencies."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

TOKEN_URL = "https://log.wien/auth/realms/logwien/protocol/openid-connect/token"
API_BASE  = "https://api.wstw.at/gateway/WN_SMART_METER_API/1.0"


class WNAPIClient:
    """Thin wrapper around the two Wiener Netze Smart Meter API calls."""

    def __init__(self, client_id: str, client_secret: str, api_key: str) -> None:
        self._client_id     = client_id
        self._client_secret = client_secret
        self._api_key       = api_key
        self._token: str | None = None
        self._token_expires_at: float = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Return a valid Bearer token, fetching a new one when expired."""
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        body = urllib.parse.urlencode({
            "client_id":     self._client_id,
            "client_secret": self._client_secret,
            "grant_type":    "client_credentials",
        }).encode()

        req = urllib.request.Request(
            TOKEN_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept":       "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        self._token            = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 300)
        return self._token

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_quarter_hour_values(self, date_from: str, date_to: str) -> list:
        """Fetch 15-min readings for all meters between date_from and date_to.

        Returns the raw API list:
        [{"zaehlpunkt": "AT...", "zaehlwerke": [{"obisCode": ..., "messwerte": [...]}]}]
        """
        token  = self._get_token()
        params = urllib.parse.urlencode({
            "datumVon": date_from,
            "datumBis": date_to,
            "wertetyp": "QUARTER_HOUR",
        })
        url = f"{API_BASE}/zaehlpunkte/messwerte?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization":  f"Bearer {token}",
                "x-Gateway-APIKey": self._api_key,
                "Accept":           "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def get_anlagendaten(self) -> list:
        """Return list of meter-point dicts by calling the data endpoint."""
        today     = date.today().strftime("%Y-%m-%d")
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        raw       = self.get_quarter_hour_values(date_from=yesterday, date_to=today)
        return [{"zaehlpunkt": zp["zaehlpunkt"]} for zp in raw if "zaehlpunkt" in zp]
