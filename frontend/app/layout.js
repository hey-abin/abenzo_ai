import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata = {
  title: "Abenzo AI - Sales Assistant MVP",
  description: "Local-first AI sales assistant for Abenzo Web Development Agency",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-50 font-sans text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-100">
        <Navbar />
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          {children}
        </main>
      </body>
    </html>
  );
}
