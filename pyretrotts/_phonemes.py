# Phoneme enum values from mt4.h
# Odd-numbered: 1/3 of a phoneme length, Even: normal length (from Appendix.c)

# Phoneme enum (mt4.h line 288-315)
# These are the core phonemes in order
(
    _IY_, _IH_, _EH_, _AE_, _AA_, _AH_, _AO_, _UH_, _AX_, _ER_,
    _EY_, _AY_, _OY_, _AW_, _OW_, _UW_, _YU_, _IR_, _XR_, _AR_,
    _OR_, _UR_, _IX_, _SIL_, _RX_, _LX_, _EL_, _EN_, _w_, _y_,
    _r_, _l_, _h_, _m_, _n_, _NG_, _f_, _v_, _TH_, _DH_,
    _s_, _z_, _SH_, _ZH_, _p_, _b_, _t_, _d_, _k_, _g_,
    _CH_, _JH_, _TX_, _DX_, _QX_, _DD_,
    _Stress1_, _Stress2_, _EmphStress_,
    _pRise_, _pFall_, _dInc_, _dDec_,
    _Syll_, _Word_, _Prep_, _Verb_,
    _Comma_, _Period_, _Quest_, _Exclam_,
    _Comp_, _Para_, _EmphWord_, _FuncWord_
) = range(75)

kNumOfPhons = _Para_ + 1  # 73

__all__ = [
    '_IY_', '_IH_', '_EH_', '_AE_', '_AA_', '_AH_', '_AO_', '_UH_', '_AX_', '_ER_',
    '_EY_', '_AY_', '_OY_', '_AW_', '_OW_', '_UW_', '_YU_', '_IR_', '_XR_', '_AR_',
    '_OR_', '_UR_', '_IX_', '_SIL_', '_RX_', '_LX_', '_EL_', '_EN_', '_w_', '_y_',
    '_r_', '_l_', '_h_', '_m_', '_n_', '_NG_', '_f_', '_v_', '_TH_', '_DH_',
    '_s_', '_z_', '_SH_', '_ZH_', '_p_', '_b_', '_t_', '_d_', '_k_', '_g_',
    '_CH_', '_JH_', '_TX_', '_DX_', '_QX_', '_DD_',
    '_Stress1_', '_Stress2_', '_EmphStress_',
    '_pRise_', '_pFall_', '_dInc_', '_dDec_',
    '_Syll_', '_Word_', '_Prep_', '_Verb_',
    '_Comma_', '_Period_', '_Quest_', '_Exclam_',
    '_Comp_', '_Para_', '_EmphWord_', '_FuncWord_',
    'kNumOfPhons', 'PHONEME_NAMES', 'PHONEME_NAMES_BY_INDEX',
    'PHONEME_STRINGS', 'PHONEME_TYPE',
    'kFirstVowel', 'kLastVowel', 'kNumPhoneme', 'kNumOfPhoneme', 'kNn',
]

# Phoneme name to index mapping
PHONEME_NAMES = {
    'IY': _IY_, 'IH': _IH_, 'EH': _EH_, 'AE': _AE_,
    'AA': _AA_, 'AH': _AH_, 'AO': _AO_, 'UH': _UH_,
    'AX': _AX_, 'ER': _ER_, 'EY': _EY_, 'AY': _AY_,
    'OY': _OY_, 'AW': _AW_, 'OW': _OW_, 'UW': _UW_,
    'YU': _YU_, 'IR': _IR_, 'XR': _XR_, 'AR': _AR_,
    'OR': _OR_, 'UR': _UR_, 'IX': _IX_,
    'SIL': _SIL_, 'RX': _RX_, 'LX': _LX_,
    'EL': _EL_, 'EN': _EN_,
    'w': _w_, 'y': _y_, 'r': _r_, 'l': _l_,
    'h': _h_, 'm': _m_, 'n': _n_,
    'NG': _NG_, 'f': _f_, 'v': _v_,
    'TH': _TH_, 'DH': _DH_, 's': _s_, 'z': _z_,
    'SH': _SH_, 'ZH': _ZH_,
    'p': _p_, 'b': _b_, 't': _t_, 'd': _d_,
    'k': _k_, 'g': _g_, 'CH': _CH_, 'JH': _JH_,
    'TX': _TX_, 'DX': _DX_, 'QX': _QX_, 'DD': _DD_,
    'Stress1': _Stress1_, 'Stress2': _Stress2_, 'EmphStress': _EmphStress_,
    'pRise': _pRise_, 'pFall': _pFall_,
    'dInc': _dInc_, 'dDec': _dDec_,
    'Syll': _Syll_, 'Word': _Word_,
    'Prep': _Prep_, 'Verb': _Verb_,
    'Comma': _Comma_, 'Period': _Period_,
    'Quest': _Quest_, 'Exclam': _Exclam_,
    'Comp': _Comp_, 'Para': _Para_,
    'EmphWord': _EmphWord_, 'FuncWord': _FuncWord_,
}

# Reverse mapping: index → name
PHONEME_NAMES_BY_INDEX = {v: k for k, v in PHONEME_NAMES.items()}

# Phoneme lookup table used by the rule engine
# These strings represent the phoneme names as used in the C code
# (lower case for most, uppercase for some like NG, TH, etc.)
PHONEME_STRINGS = [
    'IY', 'IH', 'EH', 'AE', 'AA', 'AH', 'AO', 'UH', 'AX', 'ER',
    'EY', 'AY', 'OY', 'AW', 'OW', 'UW', 'YU', 'IR', 'XR', 'AR',
    'OR', 'UR', 'IX', 'SIL', 'RX', 'LX', 'EL', 'EN', 'w', 'y',
    'r', 'l', 'h', 'm', 'n', 'NG', 'f', 'v', 'TH', 'DH',
    's', 'z', 'SH', 'ZH', 'p', 'b', 't', 'd', 'k', 'g',
    'CH', 'JH', 'TX', 'DX', 'QX', 'DD',
    'Stress1', 'Stress2', 'EmphStress',
    'pRise', 'pFall', 'dInc', 'dDec',
    'Syll', 'Word', 'Prep', 'Verb',
    'Comma', 'Period', 'Quest', 'Exclam',
    'Comp', 'Para', 'EmphWord', 'FuncWord',
]

# Phoneme categories (from Data.h phonFlags table)
# kVowelF / kConsonantF / etc.
# Values computed from the C phonFlags2 table (simplified)
PHONEME_TYPE = {
    # Vowels (kVowelF)
    'IY': 'vowel', 'IH': 'vowel', 'EH': 'vowel', 'AE': 'vowel',
    'AA': 'vowel', 'AH': 'vowel', 'AO': 'vowel', 'UH': 'vowel',
    'AX': 'vowel', 'ER': 'vowel', 'EY': 'vowel', 'AY': 'vowel',
    'OY': 'vowel', 'AW': 'vowel', 'OW': 'vowel', 'UW': 'vowel',
    'YU': 'vowel', 'IX': 'vowel',
    # Diphthongs are also vowels
    'IR': 'vowel', 'XR': 'vowel', 'AR': 'vowel',
    'OR': 'vowel', 'UR': 'vowel',
    # Consonants - voiced
    'w': 'cons', 'y': 'cons', 'r': 'cons', 'l': 'cons', 'LX': 'cons',
    'm': 'cons', 'n': 'cons', 'NG': 'cons', 'EL': 'cons', 'EN': 'cons',
    'v': 'cons', 'DH': 'cons', 'z': 'cons', 'ZH': 'cons',
    'b': 'cons', 'd': 'cons', 'g': 'cons',
    'JH': 'cons', 'DD': 'cons',
    # Consonants - unvoiced
    'h': 'cons', 'f': 'cons', 'TH': 'cons', 's': 'cons', 'SH': 'cons',
    'p': 'cons', 't': 'cons', 'k': 'cons',
    'CH': 'cons', 'TX': 'cons', 'DX': 'cons', 'QX': 'cons',
    'RX': 'cons',
    # Silence
    'SIL': 'silence',
}

# kVowelF values: IY, IH, EH, AE, AA, AH, AO, UH, AX, ER = first 10
# Plus EY, AY, OY, AW, OW, UW
# Plus YU
# Plus IX
# Plus IR, XR, AR, OR, UR (r-colored vowels)
kFirstVowel = _IY_
kLastVowel = _IX_  # last vowel before _SIL_ (index 22); IR/XR/AR/OR/UR (17-21) are r-colored vowels within this range

# The phoneme count actually used for lookup tables: _IY_(0) through _DD_(55) inclusive = 56 entries
kNumPhoneme = 56
kNumOfPhoneme = kNumPhoneme + 1

# The kNn sentinel used in phoneme tables
kNn = -1
