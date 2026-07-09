

# Encontrar el start code

START_CODE_3 = b'\x00\x00\x01'
START_CODE_4 = b'\x00\x00\x00\x01'
nal_units = []

# Pasos: 
# 1. obtener los indices de las posiciones de cada uno
# 2. Obtener el final de cada nal Unit
# 3. Recuperar las NAL Units
# 4. Mapear las NAl Units en acorde con su tipo

def recover_start_positions(data):
    positions = []
    # Se va a guardar una lista de tuplas (pos, tam)
    i = 0

    while i < len(data) -3:
        if data[i:i+4] == START_CODE_4:
            positions.append((i,4))
            i += 4
        elif data[i:i+3] == START_CODE_3:
            positions.append((i,3))
            i += 3
        else: 
            i += 1
        
    return positions

def extract_nalus(data):
    starts = recover_start_positions(data)
    if not starts:
        return []
    
    nal_units = []

    for idx, (start_pos, start_len) in enumerate(starts):
        nalu_starts = start_pos + start_len

        if idx+1 < len(starts):
            end_nalu = starts[idx+1][0]
        else:
            end_nalu = len(data)

        nalu = data[nalu_starts: end_nalu]

        nal_units.append(nalu)

    return nal_units

def extract_nalus_chunk(data):
    remaining_buffer = len(data)
    starts = recover_start_positions(data)
    isEnd = False
    if not starts:
        return [],remaining_buffer
    if len(starts) < 2: # Asegurar que al menos 1 nalu exista, sino, regresa todo para obtener más
        return [], remaining_buffer
    
    nal_units = []

    for idx, (start_pos, start_len) in enumerate(starts):
        nalu_starts = start_pos + start_len

        if idx+1 < len(starts):
            end_nalu = starts[idx+1][0]
        else:
            end_nalu = len(data)
            isEnd = True

        nalu = data[nalu_starts: end_nalu]
        # Checar si el chunk al final no tiene el inicio de otro nalu 
        if not isEnd:
            nal_units.append(nalu)
        else: #El último NALU no se obtiene por seguridad
            remaining_buffer = len(nalu) + start_len
    return nal_units, remaining_buffer

# Extraer tipo de NALU
def nalu_type(nalu):
    return nalu[0] & 0x1F

def nalu_type_name(nal_type):
    names = {
        1: "non-IDR slice",
        5: "IDR slice",
        6: "SEI",
        7: "SPS",
        8: "PPS"
    }
    return names.get(nal_type, 'otro')

if __name__ == "__main__":
    with open('output.h264', 'rb') as f:
        h_264_bytes = f.read()

    nal_units = extract_nalus(h_264_bytes)

    print(f"Total de NALUS encontradas {len(nal_units)}")

    for index, nalu in enumerate(nal_units):
        nal_type = nalu_type(nalu)
        nalu_name_type = nalu_type_name(nal_type)
        print(
            f"Nalu {index: }"
            f" type = {nal_type} ({nalu_name_type})"
            f" tam = {len(nalu)}"
        )

    with open('reconstructed', 'wb') as f:
        for nalu in nal_units:
            f.write(b'\x00\x00\x00\x01' + nalu)

