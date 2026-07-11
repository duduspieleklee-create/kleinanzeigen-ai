import React, { useState, useEffect } from "react";
import axios from "axios";

interface SearchSuggestionsProps {
  query: string;
  onSelectSuggestion: (suggestion: string) => void;
}

const SearchSuggestions: React.FC<SearchSuggestionsProps> = ({ query, onSelectSuggestion }) => {
  const [suggestions, setSuggestions] = useState<{
    query: string;
    suggestions: Record<string, string[]>;
  } | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.trim().length > 2) {
      const fetchSuggestions = async () => {
        try {
          setLoading(true);
          const response = await axios.get(`/api/search-suggestions?query=${encodeURIComponent(query)}`);
          setSuggestions(response.data);
        } catch (err) {
          setError("Fehler beim Laden der Suchvorschläge.");
        } finally {
          setLoading(false);
        }
      };

      const debounceTimer = setTimeout(fetchSuggestions, 500);
      return () => clearTimeout(debounceTimer);
    }
  }, [query]);

  if (loading) {
    return <div className="text-gray-500 text-sm">Lade Suchvorschläge...</div>;
  }

  if (error) {
    return <div className="text-red-500 text-sm">{error}</div>;
  }

  if (!suggestions || Object.keys(suggestions.suggestions).length === 0) {
    return null;
  }

  return (
    <div className="mt-2 p-3 bg-white border rounded-lg shadow-sm">
      <h3 className="font-semibold text-gray-800">🔍 Suchvorschläge für "{query}"</h3>
      <ul className="mt-2 space-y-2">
        {Object.entries(suggestions.suggestions).map(([category, terms], index) => (
          <li key={index} className="text-sm">
            <strong>{category}:</strong>
            <ul className="mt-1 pl-4 space-y-1">
              {terms.map((term, termIndex) => (
                <li
                  key={termIndex}
                  className="cursor-pointer hover:text-blue-600"
                  onClick={() => onSelectSuggestion(term)}
                >
                  {term}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default SearchSuggestions;