import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    role?: "admin" | "viewer";
    provider?: string | null;
    apiJwt?: string | null;
    user?: {
      email?: string | null;
      name?: string | null;
      image?: string | null;
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: "admin" | "viewer";
    provider?: string | null;
    apiJwt?: string | null;
  }
}
