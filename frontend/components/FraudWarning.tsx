"""
Frontend-Komponente für Betrugswarnungen.

Komponente: FraudWarning
- Zeigt Warnungen in der Anzeige an (z. B. rotes Banner).
- Nutzt die API-Endpunkte für die Betrugserkennung.
"""

import React, { useState, useEffect } from "react";
import axios from "axios";

interface FraudWarningProps {
  adId: number;
  adData: {
    title: string;
    description: string;
    price: number;
    images: string[];
  };
}

const FraudWarning: React.FC<FraudWarningProps> = ({ adId, adData }) => {
  const [fraudStatus, setFraudStatus] = useState<{
    fraud_level: "low" | "medium" | "high" | "critical";
    warnings: Array<{ type: string; message: string }>;
    recommendation: string;
  } | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchFraudStatus = async () => {
      try {
        // TODO: API-Endpunkt anpassen (aktuell nur Mock)
        const response = await axios.get(`/api/ad/${adId}/fraud-status`);
        setFraudStatus(response.data);
      } catch (err) {
        setError("Fehler bei der Betrugsprüfung.");
      } finally {
        setLoading(false);
      }
    };

    fetchFraudStatus();
  }, [adId]);

  if (loading) {
    return <div>Betrugsprüfung läuft...</div>;
  }

  if (error) {
    return <div className="text-yellow-500">{error}</div>;
  }

  if (!fraudStatus) {
    return null;
  }

  // Warnstufen definieren
  const getWarningStyle = () => {
    switch (fraudStatus.fraud_level) {
      case "critical":
        return "bg-red-100 border-red-500 text-red-700";
      case "high":
        return "bg-red-50 border-red-500 text-red-700";
      case "medium":
        return "bg-yellow-50 border-yellow-500 text-yellow-700";
      case "low":
        return "bg-green-50 border-green-500 text-green-700";
      default:
        return "bg-gray-50 border-gray-500 text-gray-700";
    }
  };

  return (
    <div className={`p-4 border rounded-lg ${getWarningStyle()}`}>
      <h3 className="font-bold">⚠️ Betrugswarnung</h3>
      <p className="mt-2">
        <strong>Stufe:</strong> {fraudStatus.fraud_level.toUpperCase()}
      </p>
      {fraudStatus.warnings.length > 0 && (
        <ul className="mt-2 list-disc pl-5">
          {fraudStatus.warnings.map((warning, index) => (
            <li key={index} className="text-sm">
              {warning.message}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-sm italic">{fraudStatus.recommendation}</p>
    </div>
  );
};

export default FraudWarning;