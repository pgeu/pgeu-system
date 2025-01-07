# Generic wrappers to handle backwards incompatible changes in dependencies
import jwt


def decode_unverified_jwt(j):
    if jwt.__version__ > 2:
        return jwt.decode(j, options={'verify_signature': False})
    else:
        return jwt.decode(j, verify=False)
