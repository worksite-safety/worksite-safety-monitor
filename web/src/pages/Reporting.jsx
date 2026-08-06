import * as React from 'react';
import {useState} from "react";
import {createColumnHelper} from '@tanstack/react-table';
import {MdDeleteOutline} from 'react-icons/md';
import DateRangePickerComp from "../components/DatePickerComp";
import DataTable from "../components/DataTable";
import Wrapper from '../assets/wrappers/ChartsContainer';
import {useSelector} from "react-redux";
import customFetch, {checkForUnauthorizedResponse} from "../util/axios";
import {toast} from "react-toastify";

const VISIBLE_FIELDS = ['eventType', 'startTime', 'confidencePercentage',
  'timePeriod', 'cameraName'];

const columnHelper = createColumnHelper();

// The grid identifies rows by the event id the engine sends, which is also
// what the delete endpoint takes.
const getRowId = (row) => row.id;

export default function ControlledSort() {
  const [events, setEvents] = useState(
      'bar');
  const {isLoading, user} = useSelector((store) => store.user);
  const [rows, setRows] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [sorting, setSorting] = React.useState([
    {
      id: 'startTime',
      desc: true,
    },
  ]);
  const fieldLabels = {
    eventType: 'Event Type',
    startTime: 'Start Time',
    confidencePercentage: 'Confidence Percentage',
    timePeriod: 'Time Period',
    cameraName: 'Camera Name',
  };

  const fetchCountableEventsData = async (startDate, endDate) => {
    setLoading(true);
    try {
      const response = await customFetch.get('event/all-events');

      const jsonData = response.data;

      const modifiedRows = jsonData.map((row) => ({
        ...row,
        startTime: new Date(row.startTime).toLocaleString('en-GB', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: 'numeric',
          minute: 'numeric',
          second: 'numeric',
        }),
        timePeriod: row.timePeriod === null ? '-' : row.timePeriod,
        confidencePercentage: (row.confidencePercentage * 100).toFixed(0) + '%',
      }));

      setRows(modifiedRows);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    const today = new Date();
    const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
    oneWeekAgo.setHours(0, 0, 1);
    today.setHours(23, 59, 59);

    fetchCountableEventsData(oneWeekAgo.getTime(), today.getTime());
  }, []);

  const handleDeleteRow = async (id) => {
    try {
      const response = await customFetch.delete(`event/delete-events/${id}`);

      if (response.status === 200) {
        const updatedRows = rows.filter((row) => row.id !== id);
        setRows(updatedRows);

        const today = new Date();
        const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
        oneWeekAgo.setHours(0, 0, 1);
        today.setHours(23, 59, 59);
        fetchCountableEventsData(oneWeekAgo.getTime(), today.getTime());
      } else {
        console.error('Failed to delete the row:', response.statusText);
      }
    } catch (error) {
      console.error('Error while deleting the row:', error.message);
    }
  };
  const fetchEventsData = async (startDate, endDate) => {
    setLoading(true);
    try {
      // The second argument is the request body, not config -- the old spelling
      // passed `{headers: {...}}` as the body, so the token was never actually
      // sent here. The request interceptor now attaches it either way.
      const response = await customFetch.post(
          `/event/sendPdfEmail/${startDate}/${endDate}/${user.email}`, {});

      const jsonData = response.data;
      toast.success("Report sent successfully!");
      setEvents(jsonData);
    } catch (error) {
      console.error("Error fetching data:", error);

      if (error.response) {
        const unauthorizedError = checkForUnauthorizedResponse(error, null);
        if (unauthorizedError) {
          console.error(unauthorizedError);
        }
      }
    } finally {
      setLoading(false);
    }
  };
  // Held in state, not rebuilt per render: the table treats a new columns array
  // as new columns. This is also why `handleDeleteRow` here is the one from the
  // first render -- as it was when this list lived in `useState` for the
  // DataGrid. It closes over the initial (empty) `rows`, so the optimistic
  // filter below it clears the grid for as long as the refetch takes. That is
  // the behaviour this page has always had; fixing it is a separate change.
  const [columns] = React.useState(() => [
    ...VISIBLE_FIELDS.map((field) => columnHelper.accessor(field, {
      id: field,
      header: fieldLabels[field] || field,
    })),
    columnHelper.display({
      id: 'actions',
      header: 'Actions',
      cell: ({row}) => (
          <MdDeleteOutline
              // MUI's icons are 24px by default and react-icons' are 1em, so
              // the size is spelled out to keep the row looking the same.
              size={24}
              role="button"
              aria-label="Delete"
              style={{cursor: 'pointer'}}
              onClick={() => handleDeleteRow(row.original.id)}
          />
      ),
    }),
  ]);
  return (
      <div>
        <Wrapper style={{display: "flex", justifyContent: "flex-end"}}>

          <DateRangePickerComp onApply={fetchEventsData}
                               applyButtonLabel={"Send Report"}
                               clearButtonLabel={"Clear"}/>
        </Wrapper>

        <div style={{height: 750, width: '100%'}}>
          <DataTable
              rows={rows}
              columns={columns}
              loading={loading}
              sorting={sorting}
              onSortingChange={setSorting}
              getRowId={getRowId}
              exportFileName="reportLocalExport"
          />
        </div>
      </div>
  );
}
