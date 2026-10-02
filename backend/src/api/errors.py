from fastapi import HTTPException


def not_found(): return HTTPException(404,{"code":"NOT_FOUND","message":"Incident not found"})
def domain_error(): return HTTPException(409,{"code":"DOMAIN_RULE_VIOLATION","message":"Invalid incident state transition"})
