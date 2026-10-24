"""
Demo thresholds for hobby sensors. These are NOT certified safety limits: the
ESP32 must sound its own local alarm, and labs keep their real fire/gas alarms.
"""

from .models import Level, SafetyAlert

# Readings at or above / below these values. Gas is the MQ-2 raw ADC value (0-4095),
# uncalibrated, so treat it as "much higher than usual", not a concentration.
TEMPERATURE_C = {"warning_above": 32.0, "danger_above": 40.0, "warning_below": 10.0}
HUMIDITY_PCT = {"warning_above": 80.0, "warning_below": 15.0}
GAS_RAW = {"warning_above": 1500, "danger_above": 2500}

RANGES = {
    "temperature_c": (-40.0, 85.0),   # DHT22 range
    "humidity_pct": (0.0, 100.0),
    "gas_raw": (0, 4095),             # 12-bit ESP32 ADC
}

SEVERITY = {Level.NORMAL: 0, Level.WARNING: 1, Level.DANGER: 2}


def worst(levels):
    return max(levels, key=SEVERITY.__getitem__, default=Level.NORMAL)


def assess(temperature_c=None, humidity_pct=None, gas_raw=None):
    """Returns [(kind, level, value, message)] for every reading outside the normal range."""
    findings = []
    if temperature_c is not None:
        t = TEMPERATURE_C
        if temperature_c >= t["danger_above"]:
            findings.append((SafetyAlert.Kind.TEMPERATURE, Level.DANGER, temperature_c,
                             f"Temperature {temperature_c:.1f} °C (danger above {t['danger_above']:.0f} °C)"))
        elif temperature_c >= t["warning_above"]:
            findings.append((SafetyAlert.Kind.TEMPERATURE, Level.WARNING, temperature_c,
                             f"Temperature {temperature_c:.1f} °C (warning above {t['warning_above']:.0f} °C)"))
        elif temperature_c <= t["warning_below"]:
            findings.append((SafetyAlert.Kind.TEMPERATURE, Level.WARNING, temperature_c,
                             f"Temperature {temperature_c:.1f} °C (below {t['warning_below']:.0f} °C)"))
    if humidity_pct is not None:
        h = HUMIDITY_PCT
        if humidity_pct >= h["warning_above"]:
            findings.append((SafetyAlert.Kind.HUMIDITY, Level.WARNING, humidity_pct,
                             f"Humidity {humidity_pct:.0f}% (above {h['warning_above']:.0f}%)"))
        elif humidity_pct <= h["warning_below"]:
            findings.append((SafetyAlert.Kind.HUMIDITY, Level.WARNING, humidity_pct,
                             f"Humidity {humidity_pct:.0f}% (below {h['warning_below']:.0f}%)"))
    if gas_raw is not None:
        g = GAS_RAW
        if gas_raw >= g["danger_above"]:
            findings.append((SafetyAlert.Kind.GAS, Level.DANGER, gas_raw,
                             f"Gas sensor {gas_raw} raw (danger above {g['danger_above']})"))
        elif gas_raw >= g["warning_above"]:
            findings.append((SafetyAlert.Kind.GAS, Level.WARNING, gas_raw,
                             f"Gas sensor {gas_raw} raw (warning above {g['warning_above']})"))
    return findings
