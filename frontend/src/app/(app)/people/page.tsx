import type { Metadata } from "next";
import { PeopleClient } from "./people-client";

export const metadata: Metadata = { title: "People" };

export default function Page() {
  return <PeopleClient />;
}
