from enum import Enum
from typing import NamedTuple, cast


class CurrencyDetails(NamedTuple):
    code: str
    name: str
    minor_units: int


class Currency(Enum):
    AED = CurrencyDetails(code="AED", name="UAE Dirham", minor_units=2)
    AFN = CurrencyDetails(code="AFN", name="Afghani", minor_units=2)
    ALL = CurrencyDetails(code="ALL", name="Lek", minor_units=2)
    AMD = CurrencyDetails(code="AMD", name="Armenian Dram", minor_units=2)
    ANG = CurrencyDetails(code="ANG", name="Netherlands Antillean Guilder", minor_units=2)
    AOA = CurrencyDetails(code="AOA", name="Kwanza", minor_units=2)
    ARS = CurrencyDetails(code="ARS", name="Argentine Peso", minor_units=2)
    AUD = CurrencyDetails(code="AUD", name="Australian Dollar", minor_units=2)
    AWG = CurrencyDetails(code="AWG", name="Aruban Florin", minor_units=2)
    AZN = CurrencyDetails(code="AZN", name="Azerbaijan Manat", minor_units=2)
    BAM = CurrencyDetails(code="BAM", name="Convertible Mark", minor_units=2)
    BBD = CurrencyDetails(code="BBD", name="Barbados Dollar", minor_units=2)
    BDT = CurrencyDetails(code="BDT", name="Taka", minor_units=2)
    BGN = CurrencyDetails(code="BGN", name="Bulgarian Lev", minor_units=2)
    BHD = CurrencyDetails(code="BHD", name="Bahraini Dinar", minor_units=3)
    BIF = CurrencyDetails(code="BIF", name="Burundi Franc", minor_units=0)
    BMD = CurrencyDetails(code="BMD", name="Bermudian Dollar", minor_units=2)
    BND = CurrencyDetails(code="BND", name="Brunei Dollar", minor_units=2)
    BOB = CurrencyDetails(code="BOB", name="Boliviano", minor_units=2)
    BOV = CurrencyDetails(code="BOV", name="Mvdol", minor_units=2)
    BRL = CurrencyDetails(code="BRL", name="Brazilian Real", minor_units=2)
    BSD = CurrencyDetails(code="BSD", name="Bahamian Dollar", minor_units=2)
    BTN = CurrencyDetails(code="BTN", name="Ngultrum", minor_units=2)
    BWP = CurrencyDetails(code="BWP", name="Pula", minor_units=2)
    BYN = CurrencyDetails(code="BYN", name="Belarusian Ruble", minor_units=2)
    BZD = CurrencyDetails(code="BZD", name="Belize Dollar", minor_units=2)
    CAD = CurrencyDetails(code="CAD", name="Canadian Dollar", minor_units=2)
    CDF = CurrencyDetails(code="CDF", name="Congolese Franc", minor_units=2)
    CHE = CurrencyDetails(code="CHE", name="WIR Euro", minor_units=2)
    CHF = CurrencyDetails(code="CHF", name="Swiss Franc", minor_units=2)
    CHW = CurrencyDetails(code="CHW", name="WIR Franc", minor_units=2)
    CLF = CurrencyDetails(code="CLF", name="Unidad de Fomento", minor_units=4)
    CLP = CurrencyDetails(code="CLP", name="Chilean Peso", minor_units=0)
    CNY = CurrencyDetails(code="CNY", name="Yuan Renminbi", minor_units=2)
    COP = CurrencyDetails(code="COP", name="Colombian Peso", minor_units=2)
    COU = CurrencyDetails(code="COU", name="Unidad de Valor Real", minor_units=2)
    CRC = CurrencyDetails(code="CRC", name="Costa Rican Colon", minor_units=2)
    CUC = CurrencyDetails(code="CUC", name="Peso Convertible", minor_units=2)
    CUP = CurrencyDetails(code="CUP", name="Cuban Peso", minor_units=2)
    CVE = CurrencyDetails(code="CVE", name="Cabo Verde Escudo", minor_units=2)
    CZK = CurrencyDetails(code="CZK", name="Czech Koruna", minor_units=2)
    DJF = CurrencyDetails(code="DJF", name="Djibouti Franc", minor_units=0)
    DKK = CurrencyDetails(code="DKK", name="Danish Krone", minor_units=2)
    DOP = CurrencyDetails(code="DOP", name="Dominican Peso", minor_units=2)
    DZD = CurrencyDetails(code="DZD", name="Algerian Dinar", minor_units=2)
    EGP = CurrencyDetails(code="EGP", name="Egyptian Pound", minor_units=2)
    ERN = CurrencyDetails(code="ERN", name="Nakfa", minor_units=2)
    ETB = CurrencyDetails(code="ETB", name="Ethiopian Birr", minor_units=2)
    EUR = CurrencyDetails(code="EUR", name="Euro", minor_units=2)
    FJD = CurrencyDetails(code="FJD", name="Fiji Dollar", minor_units=2)
    FKP = CurrencyDetails(code="FKP", name="Falkland Islands Pound", minor_units=2)
    GBP = CurrencyDetails(code="GBP", name="Pound Sterling", minor_units=2)
    GEL = CurrencyDetails(code="GEL", name="Lari", minor_units=2)
    GHS = CurrencyDetails(code="GHS", name="Ghana Cedi", minor_units=2)
    GIP = CurrencyDetails(code="GIP", name="Gibraltar Pound", minor_units=2)
    GMD = CurrencyDetails(code="GMD", name="Dalasi", minor_units=2)
    GNF = CurrencyDetails(code="GNF", name="Guinean Franc", minor_units=0)
    GTQ = CurrencyDetails(code="GTQ", name="Quetzal", minor_units=2)
    GYD = CurrencyDetails(code="GYD", name="Guyana Dollar", minor_units=2)
    HKD = CurrencyDetails(code="HKD", name="Hong Kong Dollar", minor_units=2)
    HNL = CurrencyDetails(code="HNL", name="Lempira", minor_units=2)
    HTG = CurrencyDetails(code="HTG", name="Gourde", minor_units=2)
    HUF = CurrencyDetails(code="HUF", name="Forint", minor_units=2)
    IDR = CurrencyDetails(code="IDR", name="Rupiah", minor_units=2)
    ILS = CurrencyDetails(code="ILS", name="New Israeli Sheqel", minor_units=2)
    INR = CurrencyDetails(code="INR", name="Indian Rupee", minor_units=2)
    IQD = CurrencyDetails(code="IQD", name="Iraqi Dinar", minor_units=3)
    IRR = CurrencyDetails(code="IRR", name="Iranian Rial", minor_units=2)
    ISK = CurrencyDetails(code="ISK", name="Iceland Krona", minor_units=0)
    JMD = CurrencyDetails(code="JMD", name="Jamaican Dollar", minor_units=2)
    JOD = CurrencyDetails(code="JOD", name="Jordanian Dinar", minor_units=3)
    JPY = CurrencyDetails(code="JPY", name="Yen", minor_units=0)
    KES = CurrencyDetails(code="KES", name="Kenyan Shilling", minor_units=2)
    KGS = CurrencyDetails(code="KGS", name="Som", minor_units=2)
    KHR = CurrencyDetails(code="KHR", name="Riel", minor_units=2)
    KMF = CurrencyDetails(code="KMF", name="Comorian Franc ", minor_units=0)
    KPW = CurrencyDetails(code="KPW", name="North Korean Won", minor_units=2)
    KRW = CurrencyDetails(code="KRW", name="Won", minor_units=0)
    KWD = CurrencyDetails(code="KWD", name="Kuwaiti Dinar", minor_units=3)
    KYD = CurrencyDetails(code="KYD", name="Cayman Islands Dollar", minor_units=2)
    KZT = CurrencyDetails(code="KZT", name="Tenge", minor_units=2)
    LAK = CurrencyDetails(code="LAK", name="Lao Kip", minor_units=2)
    LBP = CurrencyDetails(code="LBP", name="Lebanese Pound", minor_units=2)
    LKR = CurrencyDetails(code="LKR", name="Sri Lanka Rupee", minor_units=2)
    LRD = CurrencyDetails(code="LRD", name="Liberian Dollar", minor_units=2)
    LSL = CurrencyDetails(code="LSL", name="Loti", minor_units=2)
    LYD = CurrencyDetails(code="LYD", name="Libyan Dinar", minor_units=3)
    MAD = CurrencyDetails(code="MAD", name="Moroccan Dirham", minor_units=2)
    MDL = CurrencyDetails(code="MDL", name="Moldovan Leu", minor_units=2)
    MGA = CurrencyDetails(code="MGA", name="Malagasy Ariary", minor_units=2)
    MKD = CurrencyDetails(code="MKD", name="Denar", minor_units=2)
    MMK = CurrencyDetails(code="MMK", name="Kyat", minor_units=2)
    MNT = CurrencyDetails(code="MNT", name="Tugrik", minor_units=2)
    MOP = CurrencyDetails(code="MOP", name="Pataca", minor_units=2)
    MRU = CurrencyDetails(code="MRU", name="Ouguiya", minor_units=2)
    MUR = CurrencyDetails(code="MUR", name="Mauritius Rupee", minor_units=2)
    MVR = CurrencyDetails(code="MVR", name="Rufiyaa", minor_units=2)
    MWK = CurrencyDetails(code="MWK", name="Malawi Kwacha", minor_units=2)
    MXN = CurrencyDetails(code="MXN", name="Mexican Peso", minor_units=2)
    MXV = CurrencyDetails(code="MXV", name="Mexican Unidad de Inversion (UDI)", minor_units=2)
    MYR = CurrencyDetails(code="MYR", name="Malaysian Ringgit", minor_units=2)
    MZN = CurrencyDetails(code="MZN", name="Mozambique Metical", minor_units=2)
    NAD = CurrencyDetails(code="NAD", name="Namibia Dollar", minor_units=2)
    NGN = CurrencyDetails(code="NGN", name="Naira", minor_units=2)
    NIO = CurrencyDetails(code="NIO", name="Cordoba Oro", minor_units=2)
    NOK = CurrencyDetails(code="NOK", name="Norwegian Krone", minor_units=2)
    NPR = CurrencyDetails(code="NPR", name="Nepalese Rupee", minor_units=2)
    NZD = CurrencyDetails(code="NZD", name="New Zealand Dollar", minor_units=2)
    OMR = CurrencyDetails(code="OMR", name="Rial Omani", minor_units=3)
    PAB = CurrencyDetails(code="PAB", name="Balboa", minor_units=2)
    PEN = CurrencyDetails(code="PEN", name="Sol", minor_units=2)
    PGK = CurrencyDetails(code="PGK", name="Kina", minor_units=2)
    PHP = CurrencyDetails(code="PHP", name="Philippine Peso", minor_units=2)
    PKR = CurrencyDetails(code="PKR", name="Pakistan Rupee", minor_units=2)
    PLN = CurrencyDetails(code="PLN", name="Zloty", minor_units=2)
    PYG = CurrencyDetails(code="PYG", name="Guarani", minor_units=0)
    QAR = CurrencyDetails(code="QAR", name="Qatari Rial", minor_units=2)
    RON = CurrencyDetails(code="RON", name="Romanian Leu", minor_units=2)
    RSD = CurrencyDetails(code="RSD", name="Serbian Dinar", minor_units=2)
    RUB = CurrencyDetails(code="RUB", name="Russian Ruble", minor_units=2)
    RWF = CurrencyDetails(code="RWF", name="Rwanda Franc", minor_units=0)
    SAR = CurrencyDetails(code="SAR", name="Saudi Riyal", minor_units=2)
    SBD = CurrencyDetails(code="SBD", name="Solomon Islands Dollar", minor_units=2)
    SCR = CurrencyDetails(code="SCR", name="Seychelles Rupee", minor_units=2)
    SDG = CurrencyDetails(code="SDG", name="Sudanese Pound", minor_units=2)
    SEK = CurrencyDetails(code="SEK", name="Swedish Krona", minor_units=2)
    SGD = CurrencyDetails(code="SGD", name="Singapore Dollar", minor_units=2)
    SHP = CurrencyDetails(code="SHP", name="Saint Helena Pound", minor_units=2)
    SLE = CurrencyDetails(code="SLE", name="Leone", minor_units=2)
    SLL = CurrencyDetails(code="SLL", name="Leone", minor_units=2)
    SOS = CurrencyDetails(code="SOS", name="Somali Shilling", minor_units=2)
    SRD = CurrencyDetails(code="SRD", name="Surinam Dollar", minor_units=2)
    SSP = CurrencyDetails(code="SSP", name="South Sudanese Pound", minor_units=2)
    STN = CurrencyDetails(code="STN", name="Dobra", minor_units=2)
    SVC = CurrencyDetails(code="SVC", name="El Salvador Colon", minor_units=2)
    SYP = CurrencyDetails(code="SYP", name="Syrian Pound", minor_units=2)
    SZL = CurrencyDetails(code="SZL", name="Lilangeni", minor_units=2)
    THB = CurrencyDetails(code="THB", name="Baht", minor_units=2)
    TJS = CurrencyDetails(code="TJS", name="Somoni", minor_units=2)
    TMT = CurrencyDetails(code="TMT", name="Turkmenistan New Manat", minor_units=2)
    TND = CurrencyDetails(code="TND", name="Tunisian Dinar", minor_units=3)
    TOP = CurrencyDetails(code="TOP", name="Pa’anga", minor_units=2)
    TRY = CurrencyDetails(code="TRY", name="Turkish Lira", minor_units=2)
    TTD = CurrencyDetails(code="TTD", name="Trinidad and Tobago Dollar", minor_units=2)
    TWD = CurrencyDetails(code="TWD", name="New Taiwan Dollar", minor_units=2)
    TZS = CurrencyDetails(code="TZS", name="Tanzanian Shilling", minor_units=2)
    UAH = CurrencyDetails(code="UAH", name="Hryvnia", minor_units=2)
    UGX = CurrencyDetails(code="UGX", name="Uganda Shilling", minor_units=0)
    USD = CurrencyDetails(code="USD", name="US Dollar", minor_units=2)
    USN = CurrencyDetails(code="USN", name="US Dollar (Next day)", minor_units=2)
    UYI = CurrencyDetails(code="UYI", name="Uruguay Peso en Unidades Indexadas (UI)", minor_units=0)
    UYU = CurrencyDetails(code="UYU", name="Peso Uruguayo", minor_units=2)
    UYW = CurrencyDetails(code="UYW", name="Unidad Previsional", minor_units=4)
    UZS = CurrencyDetails(code="UZS", name="Uzbekistan Sum", minor_units=2)
    VED = CurrencyDetails(code="VED", name="Bolívar Soberano", minor_units=2)
    VES = CurrencyDetails(code="VES", name="Bolívar Soberano", minor_units=2)
    VND = CurrencyDetails(code="VND", name="Dong", minor_units=0)
    VUV = CurrencyDetails(code="VUV", name="Vatu", minor_units=0)
    WST = CurrencyDetails(code="WST", name="Tala", minor_units=2)
    XAF = CurrencyDetails(code="XAF", name="CFA Franc BEAC", minor_units=0)
    XCD = CurrencyDetails(code="XCD", name="East Caribbean Dollar", minor_units=2)
    XOF = CurrencyDetails(code="XOF", name="CFA Franc BCEAO", minor_units=0)
    XPF = CurrencyDetails(code="XPF", name="CFP Franc", minor_units=0)
    YER = CurrencyDetails(code="YER", name="Yemeni Rial", minor_units=2)
    ZAR = CurrencyDetails(code="ZAR", name="Rand", minor_units=2)
    ZMW = CurrencyDetails(code="ZMW", name="Zambian Kwacha", minor_units=2)
    ZWL = CurrencyDetails(code="ZWL", name="Zimbabwe Dollar", minor_units=2)

    @staticmethod
    def from_code(code: str) -> "Currency":
        return cast(Currency, getattr(Currency, code))

    @staticmethod
    def allcodes() -> set[str]:
        return {c.code for c in Currency}

    @property
    def code(self) -> str:
        return self.value.code

    @property
    def name(self) -> str:
        return self.value.name

    @property
    def minor_units(self) -> int:
        return self.value.minor_units
