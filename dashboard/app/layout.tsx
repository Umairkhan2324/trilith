import "@fontsource-variable/manrope";
import "@fontsource-variable/newsreader";
import "./globals.css";
import { ToastProvider } from "@/components/Toaster";

export const metadata = {
  title: "Trilith Observatory",
  description: "Read, change, and watch the context Trilith keeps, ranks, and releases.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
