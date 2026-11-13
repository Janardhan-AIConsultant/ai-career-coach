import { useQuery } from "@tanstack/react-query";
import { getHealth } from "./api/client";

export default function App() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["health"], queryFn: getHealth });
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl font-bold">AI Career Coach</h1>
      <p className="mt-2 text-gray-600">Platform scaffold. Career services arrive in later phases.</p>
      <p role="status" className="mt-4">
        API: {isLoading ? "checking…" : isError ? "unreachable" : data?.status}
      </p>
    </main>
  );
}
