import { createContext, useContext, useEffect, useState } from "react";

import {
  getModelOptions,
  type ModelOptionsResponse,
  type ModelProvider,
} from "../api/client";

interface WorkbenchState {
  modelOptions: ModelOptionsResponse | null;
  modelOptionsError: string | null;
  selectedProvider: ModelProvider | null;
  setSelectedProvider: (provider: ModelProvider) => void;
}

const WorkbenchContext = createContext<WorkbenchState | null>(null);

export function WorkbenchProvider({ children }: { children: React.ReactNode }) {
  const [modelOptions, setModelOptions] = useState<ModelOptionsResponse | null>(
    null,
  );
  const [modelOptionsError, setModelOptionsError] = useState<string | null>(
    null,
  );
  const [selectedProvider, setSelectedProvider] =
    useState<ModelProvider | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getModelOptions(controller.signal)
      .then((options) => {
        setModelOptions(options);
        setSelectedProvider((current) => current ?? options.default_provider);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setModelOptionsError(
            "Model settings are unavailable from the backend.",
          );
        }
      });

    return () => controller.abort();
  }, []);

  return (
    <WorkbenchContext.Provider
      value={{
        modelOptions,
        modelOptionsError,
        selectedProvider,
        setSelectedProvider,
      }}
    >
      {children}
    </WorkbenchContext.Provider>
  );
}

export function useWorkbench(): WorkbenchState {
  const context = useContext(WorkbenchContext);
  if (context === null) {
    throw new Error("useWorkbench must be used inside WorkbenchProvider");
  }
  return context;
}
