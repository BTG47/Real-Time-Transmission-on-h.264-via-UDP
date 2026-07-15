from enum import IntEnum

class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3

def obtain_classification_nalu(nal_type_str):
    CRITICAL_VALUES = ['SPS', 'PPS']
    HIGH_VALUES = ['IDR slice']
    NORMAL_VALUES = ['non-IDR slice', 'otro']
    LOW_VALUES = ['SEI']

    if nal_type_str in CRITICAL_VALUES:
        return Priority.CRITICAL
    elif nal_type_str in HIGH_VALUES:
        return Priority.HIGH
    elif nal_type_str in NORMAL_VALUES:
        return Priority.NORMAL
    elif nal_type_str in LOW_VALUES:
        return Priority.LOW
    else:
        return Priority.LOW