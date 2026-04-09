import math
import time

class OneEuroFilter:
    def __init__(self, t0, x0, dx0=0.0, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = x0
        self.dx_prev = dx0
        self.t_prev = t0

    def __call__(self, t, x):
        t_e = t - self.t_prev
        if t_e <= 0:
            return x

        # Gürültülü hızı hesapla
        dx = (x - self.x_prev) / t_e
        dx_res = self._exp_smoothing(self._alpha(t_e, self.d_cutoff), dx, self.dx_prev)

        # Hıza bağlı cutoff frekansı
        cutoff = self.min_cutoff + self.beta * abs(dx_res)
        x_res = self._exp_smoothing(self._alpha(t_e, cutoff), x, self.x_prev)

        self.x_prev = x_res
        self.dx_prev = dx_res
        self.t_prev = t

        return x_res

    def _alpha(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

    def _exp_smoothing(self, alpha, x, x_prev):
        return alpha * x + (1 - alpha) * x_prev