import enum


class HeAacSignaling(enum.Enum):
    DEFAULT = 'DEFAULT'
    IMPLICIT = 'IMPLICIT'
    EXPLICIT_SBR = 'EXPLICIT_SBR'
    EXPLICIT_HIERARCHICAL = 'EXPLICIT_HIERARCHICAL'
