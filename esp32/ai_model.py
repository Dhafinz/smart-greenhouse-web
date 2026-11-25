# Edge AI Decision Tree murni Python untuk ESP32 MicroPython
# Tanpa library eksternal (scikit-learn/micromlgen), hemat RAM dan instan.

PLANT_MAP = {
    "aglaonema": 0,
    "alocasia": 1,
    "anggrek_bulan": 2,
    "anthurium": 3,
    "begonia_rex": 4,
    "calathea": 5,
    "fittonia": 6,
    "kaktus_mini": 7,
    "kamboja_jepang": 8,
    "keladi_hias": 9,
    "krisan_mini": 10,
    "lidah_buaya": 11,
    "lidah_mertua": 12,
    "maranta": 13,
    "mawar_mini": 14,
    "monstera": 15,
    "pakis_boston": 16,
    "peace_lily": 17,
    "peperomia": 18,
    "philodendron": 19,
    "pilea": 20,
    "sirih_gading": 21,
    "spider_plant": 22,
    "sukulen_echeveria": 23,
    "tillandsia": 24,
}

# Ambang batas ideal per tanaman_id (0..24)
# Urutan tuple: (soil_min, temp_max, light_min)
_THRESHOLDS = (
    (45, 29, 30),  # 0: aglaonema
    (50, 28, 40),  # 1: alocasia
    (35, 28, 40),  # 2: anggrek_bulan
    (50, 28, 40),  # 3: anthurium
    (45, 25, 35),  # 4: begonia_rex
    (55, 27, 25),  # 5: calathea
    (55, 26, 25),  # 6: fittonia
    (15, 35, 70),  # 7: kaktus_mini
    (25, 34, 70),  # 8: kamboja_jepang
    (50, 30, 45),  # 9: keladi_hias
    (45, 26, 60),  # 10: krisan_mini
    (20, 32, 65),  # 11: lidah_buaya
    (20, 32, 35),  # 12: lidah_mertua
    (50, 27, 30),  # 13: maranta
    (50, 27, 65),  # 14: mawar_mini
    (45, 29, 40),  # 15: monstera
    (60, 26, 30),  # 16: pakis_boston
    (50, 28, 25),  # 17: peace_lily
    (35, 27, 35),  # 18: peperomia
    (45, 29, 35),  # 19: philodendron
    (40, 26, 45),  # 20: pilea
    (40, 30, 30),  # 21: sirih_gading
    (40, 27, 40),  # 22: spider_plant
    (15, 32, 70),  # 23: sukulen_echeveria
    (10, 30, 50),  # 24: tillandsia
)


def _pred_pompa(tanaman_id, tanah):
    """Decision node untuk pompa air: ON (1) jika tanah < soil_min."""
    if 0 <= tanaman_id < len(_THRESHOLDS):
        soil_min = _THRESHOLDS[tanaman_id][0]
    else:
        soil_min = 45
    return 1 if tanah < soil_min else 0


def _pred_kipas(tanaman_id, suhu):
    """Decision node untuk kipas: ON (1) jika suhu > temp_max."""
    if 0 <= tanaman_id < len(_THRESHOLDS):
        temp_max = _THRESHOLDS[tanaman_id][1]
    else:
        temp_max = 29
    return 1 if suhu > temp_max else 0


def _pred_lampu(tanaman_id, cahaya):
    """Decision node untuk lampu: ON (1) jika cahaya < light_min."""
    if 0 <= tanaman_id < len(_THRESHOLDS):
        light_min = _THRESHOLDS[tanaman_id][2]
    else:
        light_min = 40
    return 1 if cahaya < light_min else 0


def prediksi_ai(nama_tanaman, suhu, kelembapan, tanah, cahaya):
    """Mengembalikan keputusan (pompa, kipas, lampu) secara terpisah per aktuator."""
    tanaman_id = PLANT_MAP.get(nama_tanaman, 15)  # Default: monstera (15)
    p = _pred_pompa(tanaman_id, tanah)
    k = _pred_kipas(tanaman_id, suhu)
    l = _pred_lampu(tanaman_id, cahaya)
    return (p, k, l)
