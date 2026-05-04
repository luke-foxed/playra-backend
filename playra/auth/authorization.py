from pyramid.security import Authenticated


class SupabaseAuthorizationPolicy:

    def permits(self, context, principals, permission):
        if permission == "authenticated":
            return Authenticated in principals

        return True