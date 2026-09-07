from pathlib import Path
import pytest
from srw4.en_scarlet_upgrade import install, SCARLET_INDEX_PC
from srw4.en_story_build import verify_stock_objectives

ROOT = Path(__file__).resolve().parents[1]

def baseline():
    return (ROOT/'rom/Dai-4-ji Super Robot Taisen (English combo).sfc').read_bytes()

def test_only_diana_scarlet_index_changes():
    original = baseline()
    image = bytearray(original)
    install(image)
    assert [(i, a, b) for i, (a, b) in enumerate(zip(original, image)) if a != b] == [(SCARLET_INDEX_PC, 3, 0)]
    verify_stock_objectives(image, original)

@pytest.mark.parametrize('address', [SCARLET_INDEX_PC, 0xB9C7A, 0xB3A6, 0x2F5DF])
def test_incompatible_or_old_patch_is_rejected_atomically(address):
    image = bytearray(baseline())
    image[address] ^= 1
    before = bytes(image)
    with pytest.raises(ValueError):
        install(image)
    assert image == before
