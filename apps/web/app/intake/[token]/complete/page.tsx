import { Card, CardContent } from "@/components/ui/card";

export default function IntakeCompletePage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md text-center">
        <CardContent className="pt-8 pb-8">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6 text-primary"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold">Form submitted!</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Thank you for completing your intake form. We look forward to seeing you at your
            appointment.
          </p>
          <p className="mt-4 text-xs text-muted-foreground">
            You may close this window.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
