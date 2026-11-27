        self.last_power_loss = dt_util.parse_datetime(stored.get("last_power_loss") or "")
        self.last_power_restored = dt_util.parse_datetime(stored.get("last_power_restored") or "")
