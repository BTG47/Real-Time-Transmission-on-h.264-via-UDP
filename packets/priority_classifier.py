from enum import IntEnum


class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3

def obtain_classification_nalu(nal_type_int):
    from config import CRITICAL_VALUES, HIGH_VALUES, NORMAL_VALUES, LOW_VALUES

    if nal_type_int in CRITICAL_VALUES:
        return Priority.CRITICAL
    elif nal_type_int in HIGH_VALUES:
        return Priority.HIGH
    elif nal_type_int in NORMAL_VALUES:
        return Priority.NORMAL
    elif nal_type_int in LOW_VALUES:
        return Priority.LOW
    else:
        return Priority.NORMAL