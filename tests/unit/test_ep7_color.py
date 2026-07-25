import numpy as np
import pytest
from PIL import Image
from ai.color_index import compute_color_signature, rgb_to_histogram, color_search


def _img(tmp_path, name, rgb):
    p = tmp_path / name
    Image.new("RGB", (32, 32), rgb).save(str(p))
    return str(p)


@pytest.mark.unit
def test_signature_histogram_normalized_and_red_peaks(tmp_path):
    sig = compute_color_signature(_img(tmp_path, "red.png", (255, 0, 0)))
    assert sig is not None
    hist = sig["histogram"]
    assert hist.shape == (12,)
    assert abs(float(hist.sum()) - 1.0) < 1e-4
    # red hue ~0 -> first bin dominates
    assert int(np.argmax(hist)) == 0


@pytest.mark.unit
def test_signature_none_on_missing_file():
    assert compute_color_signature("/no/such/file.png") is None


@pytest.mark.unit
def test_color_search_ranks_matching_color_first(stax_db, tmp_path):
    stax_db.create_stack("S", "/tmp/S")
    with stax_db.get_connection() as conn:
        conn.execute("INSERT INTO lists (stack_fk,name) VALUES (1,'L')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'red','2D')")
        conn.execute("INSERT INTO elements (list_fk,name,type) VALUES (1,'blue','2D')")
    stax_db.store_element_color(1, rgb_to_histogram((255, 0, 0)), None)
    stax_db.store_element_color(2, rgb_to_histogram((0, 0, 255)), None)
    ranked = color_search(stax_db, (250, 10, 10), top_k=2)
    assert ranked[0][0] == 1
