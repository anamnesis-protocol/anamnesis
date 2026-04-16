from hiero_sdk_python import PrivateKey

target = "4617ae5d848079631e7831723494afc339474f7ab14fec967dddc752cb1abfc8"

# Replace these with your actual keys
der_key = "302e020100300506032b657004220420e5378ec88022098c2df76aa4669c85d82536549283e58da703a7080f8828c430"
hex_key = "0xe5378ec88022098c2df76aa4669c85d82536549283e58da703a7080f8828c430"

for label, k in [("DER", der_key), ("HEX", hex_key)]:
    try:
        pk = PrivateKey.from_string(k)
        pub = pk.public_key().to_bytes_raw().hex()
        if pub == target:
            print(label + ": MATCH - use this key")
        else:
            print(label + ": no match (got " + pub[:16] + "...)")
    except Exception as e:
        print(label + ": parse error - " + str(e))
