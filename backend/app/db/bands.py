BAND_EMPLOYEE = 1
BAND_SENIOR = 2
BAND_PRINCIPAL = 3

BAND_LABELS: dict[int, str] = {
    BAND_EMPLOYEE: "사원",
    BAND_SENIOR: "선임",
    BAND_PRINCIPAL: "책임",
}

DEFAULT_BAND = BAND_EMPLOYEE


def band_label(band: int) -> str:
    return BAND_LABELS.get(band, f"unknown({band})")
