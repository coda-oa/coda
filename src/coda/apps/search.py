from django.db.models import Q


def words_icontains(search_term: str, *fields: str) -> Q:
    words = search_term.strip().split()
    q = Q()
    for word in words:
        word_q = Q()
        for field in fields:
            word_q |= Q(**{f"{field}__icontains": word})
        q &= word_q
    return q
