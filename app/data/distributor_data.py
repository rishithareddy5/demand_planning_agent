# app/data/distributor_data.py

DISTRIBUTORS = [
    {"id": "D01", "email": "revanbejagam@gmail.com"},
    {"id": "D02", "email": "rishithareddyc2002@gmail.com"},
    {"id": "D03", "email": "saherwardi.mustafa@gmail.com"},
    {"id": "D04", "email": "lingaphani21@gmail.com"},
    {"id": "D05", "email": "poojithak493@gmail.com"},
]


def get_distributor_map():
    return {
        d["email"].lower(): d["id"]
        for d in DISTRIBUTORS
    }