"""Дербес деректерді қорғау: оқушы тек кодпен белгіленеді."""
import re

# Мысалы: 5А-12, 6Б-03, 11-7
CODE_RE = re.compile(r"^\d{1,2}[A-Za-zА-Яа-яӘәІіҢңҒғҮүҰұҚқӨөҺһ]?-\d{1,3}$")


def validate_student_code(code: str) -> tuple[bool, str]:
    code = (code or "").strip()
    if not code:
        return False, "Оқушы кодын енгізіңіз (мысалы: 5А-12)."
    if not CODE_RE.match(code):
        return False, ("Код «сынып-нөмір» пішінінде болуы керек, мысалы 5А-12. "
                       "Оқушының аты-жөнін енгізуге болмайды.")
    return True, ""
