def is_authenticated(user):
    try:
        return user.is_authenticated()  # Django<1.10
    except TypeError:
        return user.is_authenticated  # Django>=1.10


def is_anonymous(user):
    try:
        return user.is_anonymous()  # Django<1.10
    except TypeError:
        return user.is_anonymous  # Django>=1.10
