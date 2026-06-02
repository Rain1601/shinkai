import NextAuth, { type AuthOptions } from "next-auth";
import GitHubProvider from "next-auth/providers/github";
import GoogleProvider from "next-auth/providers/google";
import jwt from "jsonwebtoken";

const SHINKAI_OWNER_EMAILS = (process.env.SHINKAI_OWNER_EMAILS ?? "")
  .split(",")
  .map((entry) => entry.trim().toLowerCase())
  .filter(Boolean);

const SESSION_JWT_SECRET = process.env.SHINKAI_SESSION_SECRET ?? "";

function isOwner(email: string | null | undefined): boolean {
  if (!email) return false;
  return SHINKAI_OWNER_EMAILS.includes(email.trim().toLowerCase());
}

function mintApiJwt(claims: {
  email: string;
  role: "admin" | "viewer";
  name?: string;
  provider?: string;
}): string {
  if (!SESSION_JWT_SECRET) {
    throw new Error(
      "SHINKAI_SESSION_SECRET must be set so the api can verify session JWTs",
    );
  }
  const now = Math.floor(Date.now() / 1000);
  return jwt.sign(
    {
      ...claims,
      sub: claims.email,
      iat: now,
      exp: now + 60 * 60 * 12, // 12h
    },
    SESSION_JWT_SECRET,
    { algorithm: "HS256" },
  );
}

const providers = [];
if (process.env.GITHUB_ID && process.env.GITHUB_SECRET) {
  providers.push(
    GitHubProvider({
      clientId: process.env.GITHUB_ID,
      clientSecret: process.env.GITHUB_SECRET,
    }),
  );
}
if (process.env.GOOGLE_ID && process.env.GOOGLE_SECRET) {
  providers.push(
    GoogleProvider({
      clientId: process.env.GOOGLE_ID,
      clientSecret: process.env.GOOGLE_SECRET,
    }),
  );
}

export const authOptions: AuthOptions = {
  providers,
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 12, // 12h
  },
  callbacks: {
    async jwt({ token, account, user }) {
      // First sign-in: stash role + provider into the token.
      if (account && user) {
        const email = user.email ?? token.email ?? "";
        const role: "admin" | "viewer" = isOwner(email) ? "admin" : "viewer";
        token.role = role;
        token.provider = account.provider;
        if (email) token.email = email;
        if (user.name) token.name = user.name;
        try {
          token.apiJwt = mintApiJwt({
            email,
            role,
            name: user.name ?? undefined,
            provider: account.provider,
          });
        } catch {
          // No secret configured — leave apiJwt empty so the client can
          // still surface "signed in" but won't be able to mutate.
        }
      }
      return token;
    },
    async session({ session, token }) {
      session.user = {
        ...(session.user ?? {}),
        email: (token.email as string) ?? null,
        name: (token.name as string) ?? null,
      };
      // Expose the api JWT + role to the client so fetch() helpers can pin
      // it onto Authorization headers and conditionally render controls.
      (session as unknown as Record<string, unknown>).role =
        (token.role as "admin" | "viewer") ?? "viewer";
      (session as unknown as Record<string, unknown>).provider =
        (token.provider as string) ?? null;
      (session as unknown as Record<string, unknown>).apiJwt =
        (token.apiJwt as string) ?? null;
      return session;
    },
  },
  pages: {
    signIn: "/agent",
  },
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
