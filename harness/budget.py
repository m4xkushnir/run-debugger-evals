"""Hard spend cap. A call reserves its estimated cost before it starts and settles to the
actual cost afterwards, so concurrent calls can't overshoot the cap together."""

import threading


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, cap_usd, spent_usd=0.0):
        self.cap = cap_usd
        self.spent = spent_usd
        self.reserved = 0.0
        self._lock = threading.Lock()

    def reserve(self, estimate):
        with self._lock:
            if self.spent + self.reserved + estimate > self.cap:
                raise BudgetExceeded(
                    f"cap ${self.cap:.2f}: spent ${self.spent:.4f} + reserved ${self.reserved:.4f} "
                    f"+ next ${estimate:.4f} would exceed it"
                )
            self.reserved += estimate

    def settle(self, estimate, actual):
        with self._lock:
            self.reserved -= estimate
            self.spent += actual if actual is not None else estimate
