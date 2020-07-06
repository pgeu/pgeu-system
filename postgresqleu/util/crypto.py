from django.core.exceptions import ValidationError

from Cryptodome.PublicKey import RSA
from Cryptodome.Hash import SHA256, SHA1
from Cryptodome.Signature import pkcs1_15


def validate_pem_public_key(value):
    try:
        k = RSA.importKey(value)
        if k.has_private():
            raise ValidationError("This should be a public key, but contains a private key")
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError("Could not validate public key: {}".format(e))


def validate_pem_private_key(value):
    try:
        k = RSA.importKey(value)
        if not k.has_private():
            raise ValidationError("This should be a private key, but doesn't contain one")
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError("Could not validate private key: {}".format(e))


def generate_rsa_keypair(bits=2048):
    key = RSA.generate(bits)
    return (
        key.export_key().decode('utf8'),
        key.publickey().export_key().decode('utf8'),
    )


def rsa_sign_string_sha256(privatekeystr, msg):
    key = RSA.importKey(privatekeystr)
    h = SHA256.new(msg.encode('ascii'))
    sig = pkcs1_15.new(key).sign(h)
    return sig


def rsa_verify_string_sha1(publickeystr, msg, sig):
    key = RSA.importKey(publickeystr)
    h = SHA1.new(msg)
    try:
        pkcs1_15.new(key).verify(h, sig)
        return True
    except ValueError:
        # Raises ValueError if the signature is wrong
        return False
