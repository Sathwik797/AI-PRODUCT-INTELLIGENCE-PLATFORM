import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Edit2, Check, X, Loader2, AlertCircle, FolderTree } from 'lucide-react';
import type { Category } from '../types/category';
import { getCategories, createCategory, updateCategory, deleteCategory } from '../api/categoryApi';
import { getErrorMessage } from '../api/client';

export const CategoriesPage: React.FC = () => {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // New category state
  const [newCategoryName, setNewCategoryName] = useState<string>('');
  const [creating, setCreating] = useState<boolean>(false);

  // Edit category state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState<string>('');
  const [updating, setUpdating] = useState<boolean>(false);

  // Deleting state
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchCategories = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getCategories();
      setCategories(data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCategories();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCategoryName.trim()) return;

    try {
      setCreating(true);
      setError(null);
      const created = await createCategory({ name: newCategoryName.trim() });
      setCategories((prev) => [...prev, created]);
      setNewCategoryName('');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const startEditing = (category: Category) => {
    setEditingId(category.id);
    setEditName(category.name);
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditName('');
  };

  const handleUpdate = async (id: number) => {
    if (!editName.trim()) return;

    try {
      setUpdating(true);
      setError(null);
      const updated = await updateCategory(id, { name: editName.trim() });
      setCategories((prev) => prev.map((c) => (c.id === id ? updated : c)));
      setEditingId(null);
      setEditName('');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUpdating(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete category "${name}" (ID: ${id})?`)) {
      return;
    }

    try {
      setDeletingId(id);
      setError(null);
      await deleteCategory(id);
      setCategories((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <FolderTree className="w-6 h-6 text-indigo-600" />
            Categories
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage product categories for categorization and AI intelligence classification.
          </p>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-red-800">Error</h3>
            <p className="text-sm text-red-700 mt-0.5">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-red-400 hover:text-red-600 text-sm font-medium"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Create Form Card */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
          Add New Category
        </h2>
        <form onSubmit={handleCreate} className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            placeholder="e.g. Electronics, Footwear, Audio Gear"
            value={newCategoryName}
            onChange={(e) => setNewCategoryName(e.target.value)}
            disabled={creating}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-50"
          />
          <button
            type="submit"
            disabled={creating || !newCategoryName.trim()}
            className="inline-flex items-center justify-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors shadow-xs"
          >
            {creating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Creating...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Create Category
              </>
            )}
          </button>
        </form>
      </div>

      {/* Categories Table */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-xs overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">All Categories</h2>
          <span className="text-xs bg-gray-100 text-gray-700 font-medium px-2.5 py-1 rounded-full">
            {categories.length} total
          </span>
        </div>

        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center text-gray-500">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-2" />
            <p className="text-sm">Loading categories...</p>
          </div>
        ) : categories.length === 0 ? (
          <div className="py-12 text-center text-gray-500">
            <FolderTree className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-base font-medium text-gray-900">No categories found</p>
            <p className="text-sm text-gray-500 mt-1">
              Add your first category above to begin organizing products.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-gray-500 text-xs uppercase tracking-wider font-semibold">
                  <th className="py-3 px-5 w-24">ID</th>
                  <th className="py-3 px-5">Name</th>
                  <th className="py-3 px-5 w-48 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {categories.map((category) => {
                  const isEditing = editingId === category.id;
                  const isDeleting = deletingId === category.id;

                  return (
                    <tr key={category.id} className="hover:bg-gray-50/75 transition-colors">
                      <td className="py-3 px-5 font-mono text-xs text-gray-500">
                        #{category.id}
                      </td>
                      <td className="py-3 px-5">
                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              disabled={updating}
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleUpdate(category.id);
                                if (e.key === 'Escape') cancelEditing();
                              }}
                              className="px-3 py-1.5 border border-indigo-300 rounded-md text-sm focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                            />
                            <button
                              onClick={() => handleUpdate(category.id)}
                              disabled={updating || !editName.trim()}
                              className="p-1.5 text-green-600 hover:text-green-700 disabled:opacity-50"
                              title="Save"
                            >
                              {updating ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Check className="w-4 h-4" />
                              )}
                            </button>
                            <button
                              onClick={cancelEditing}
                              disabled={updating}
                              className="p-1.5 text-gray-400 hover:text-gray-600"
                              title="Cancel"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ) : (
                          <span className="font-medium text-gray-900">{category.name}</span>
                        )}
                      </td>
                      <td className="py-3 px-5 text-right">
                        {!isEditing && (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => startEditing(category)}
                              disabled={isDeleting}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-600 hover:text-indigo-600 hover:bg-gray-100 rounded-md transition-colors"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                              Rename
                            </button>
                            <button
                              onClick={() => handleDelete(category.id, category.name)}
                              disabled={isDeleting}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-red-600 hover:text-red-700 hover:bg-red-50 rounded-md transition-colors"
                            >
                              {isDeleting ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="w-3.5 h-3.5" />
                              )}
                              Delete
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
