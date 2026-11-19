from fractions import Fraction


def parse_load_kn(value: int | str | Fraction) -> Fraction:
    if type(value) not in (int, str, Fraction):
        raise ValueError('INVALID_LOAD: expected exact numeric text, integer or Fraction')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'INVALID_LOAD: {value!r}') from error
