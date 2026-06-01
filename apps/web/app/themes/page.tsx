import { redirect } from "next/navigation";

export default function ThemesIndexRedirect() {
  redirect("/runs?view=theme");
}
