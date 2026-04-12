"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, UserPlus } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { NewPatientModal } from "@/components/patients/NewPatientModal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePatients, type Patient } from "@/lib/api/patients";

const PAGE_SIZE = 20;

function formatDob(dob: string): string {
  // dob is YYYY-MM-DD — display as MM/DD/YYYY
  const [y, m, d] = dob.split("-");
  return `${m}/${d}/${y}`;
}

function formatSex(sex: Patient["sex"]): string {
  if (!sex) return "—";
  return sex.charAt(0).toUpperCase() + sex.slice(1);
}

function PatientsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const urlQ = searchParams.get("q") ?? "";
  const urlPage = Math.max(1, Number(searchParams.get("page") ?? "1"));

  const [searchInput, setSearchInput] = useState(urlQ);
  const [showNewModal, setShowNewModal] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const queryParams: Parameters<typeof usePatients>[0] = { page: urlPage, pageSize: PAGE_SIZE };
  if (urlQ) queryParams.q = urlQ;
  const { data, isLoading, isError } = usePatients(queryParams);

  // Sync URL when search input changes (debounced 300ms)
  const pushSearch = useCallback(
    (q: string, page: number) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (page > 1) params.set("page", String(page));
      const qs = params.toString();
      router.push(`/patients${qs ? `?${qs}` : ""}`);
    },
    [router],
  );

  function handleSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setSearchInput(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      pushSearch(val, 1);
    }, 300);
  }

  // Keep input in sync if URL changes externally (e.g. back/forward)
  useEffect(() => {
    setSearchInput(urlQ);
  }, [urlQ]);

  function goToPage(page: number) {
    pushSearch(urlQ, page);
  }

  const patients = data?.data ?? [];
  const meta = data?.meta;
  const totalPages = meta?.totalPages ?? 1;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Patients"
        description="Search and manage patient records"
        actions={
          <Button onClick={() => setShowNewModal(true)}>
            <UserPlus className="h-4 w-4" />
            New patient
          </Button>
        }
      />

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={searchInput}
          onChange={handleSearchChange}
          placeholder="Search patients…"
          className="pl-9"
        />
      </div>

      {/* Table */}
      {isError ? (
        <p className="text-sm text-destructive">Failed to load patients. Please refresh.</p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Date of birth</TableHead>
                <TableHead>Sex</TableHead>
                <TableHead>Phone</TableHead>
                <TableHead>Email</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    {Array.from({ length: 5 }).map((__, j) => (
                      <TableCell key={j}>
                        <div className="h-4 w-full animate-pulse rounded bg-muted" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : patients.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">
                    {urlQ ? `No patients matching "${urlQ}"` : "No patients yet."}
                  </TableCell>
                </TableRow>
              ) : (
                patients.map((patient) => (
                  <TableRow
                    key={patient.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/patients/${patient.id}`)}
                  >
                    <TableCell className="font-medium">
                      {patient.lastName}, {patient.firstName}
                    </TableCell>
                    <TableCell>{formatDob(patient.dateOfBirth)}</TableCell>
                    <TableCell>{formatSex(patient.sex)}</TableCell>
                    <TableCell>{patient.phone ?? "—"}</TableCell>
                    <TableCell>{patient.email ?? "—"}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Pagination */}
      {!isLoading && !isError && (meta?.total ?? 0) > 0 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Showing {(urlPage - 1) * PAGE_SIZE + 1}–
            {Math.min(urlPage * PAGE_SIZE, meta?.total ?? 0)} of {meta?.total ?? 0}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => goToPage(urlPage - 1)}
              disabled={urlPage <= 1}
            >
              Previous
            </Button>
            <span>
              {urlPage} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => goToPage(urlPage + 1)}
              disabled={urlPage >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <NewPatientModal open={showNewModal} onOpenChange={setShowNewModal} />
    </div>
  );
}

export default function PatientsPage() {
  return (
    <Suspense>
      <PatientsPageContent />
    </Suspense>
  );
}
