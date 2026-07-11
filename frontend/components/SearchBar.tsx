import React, { useState } from "react";
import SearchSuggestions from "./SearchSuggestions";

const SearchBar = () => {
  const [query, setQuery] = useState<string>("");

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    console.log("Suche nach:", query);
  };

  return (
    <form onSubmit={handleSearch} className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Suche nach Anzeigen..."
        className="w-full p-3 border rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {query.length > 2 && (
        <SearchSuggestions
          query={query}
          onSelectSuggestion={(suggestion) => setQuery(suggestion)}
        />
      )}
    </form>
  );
};

export default SearchBar;