"""Map Diana A's Scarlet Beam to its otherwise unused Repair upgrade level.

EN unit 0x2A starts at PC 0x0B9C87. Weapon entries start at +0x20,
with a two-byte weapon ID and a one-byte upgrade index. Only the fourth
weapon's index changes: 3 -> 0. No allocation, save migration or CPU hooks.
The native power calculator suppresses upgrade bonuses for support weapons.
"""
DIANA_RECORD_PC = 0x0B9C87
WEAPON_LIST_OFFSET = 0x20
WEAPON_ENTRY_BYTES = 3
SCARLET_INDEX_PC = DIANA_RECORD_PC + WEAPON_LIST_OFFSET + 3 * WEAPON_ENTRY_BYTES + 2
EXPECTED_WEAPONS = bytes.fromhex('5c0500 490001 830802 840003 0000')


def install(image: bytearray) -> dict:
    start = DIANA_RECORD_PC + WEAPON_LIST_OFFSET
    if image[start:start + len(EXPECTED_WEAPONS)] != EXPECTED_WEAPONS:
        raise ValueError('Diana weapon list does not match the original English ROM')
    # Explicitly reject the withdrawn allocator patch: do not combine fixes.
    for pc, expected in ((0xB9C7A, b'\x03'), (0xB3A6, bytes.fromhex('223cb480')),
                         (0x2F5DF, bytes.fromhex('862eaca40e'))):
        if image[pc:pc + len(expected)] != expected:
            raise ValueError(f'Original allocator/reader required at {pc:#x}')
    image[SCARLET_INDEX_PC] = 0
    return {'index_pc': SCARLET_INDEX_PC, 'old_index': 3, 'new_index': 0,
            'code_bytes': 0, 'allocation_changes': False,
            'save_policy': 'Use existing Repair level; no migration or reset'}
