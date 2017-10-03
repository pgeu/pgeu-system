from Crypto.Hash import SHA256
from Crypto import Random

def generate_random_token():
	s = SHA256.new()
	r = Random.new()
	s.update(r.read(250))
	return s.hexdigest()
