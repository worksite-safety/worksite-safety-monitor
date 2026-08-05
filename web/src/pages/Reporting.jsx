import * as React from 'react';
import {DataGrid, GridToolbar} from '@mui/x-data-grid';
import DateRangePickerComp from "../components/DatePickerComp";
import {useState} from "react";
import Wrapper from '../assets/wrappers/ChartsContainer';
import {useSelector} from "react-redux";
import customFetch, {checkForUnauthorizedResponse} from "../util/axios";
import {toast} from "react-toastify";
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';

const VISIBLE_FIELDS = ['eventType', 'startTime', 'confidencePercentage',
  'timePeriod', 'cameraName'];

export default function ControlledSort() {
  const [events, setEvents] = useState(
      'bar');
  const {isLoading, user} = useSelector((store) => store.user);
  const [rows, setRows] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [sortModel, setSortModel] = React.useState([
    {
      field: 'startTime',
      sort: 'desc',
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
  const [columns, setColumns] = React.useState([
    ...VISIBLE_FIELDS.map((field) => ({
      field,
      headerName: fieldLabels[field] || field,
      flex: 1,
    })),
    {
      field: 'actions',
      headerName: 'Actions',
      flex: 1,
      sortable: false,
      renderCell: (params) => (
          <DeleteOutlineIcon
              style={{cursor: 'pointer'}}
              onClick={() => handleDeleteRow(params.row.id)}
          />
      ),
    },
  ]);
  return (
      <div>
        <Wrapper style={{display: "flex", justifyContent: "flex-end"}}>

          <DateRangePickerComp onApply={fetchEventsData}
                               applyButtonLabel={"Send Report"}
                               clearButtonLabel={"Clear"}/>
        </Wrapper>

        <div style={{height: 750, width: '100%'}}>
          <DataGrid
              rows={rows}
              columns={columns}
              loading={loading}
              sortModel={sortModel}
              onSortModelChange={(newSortModel) => setSortModel(newSortModel)}
              components={{
                Toolbar: GridToolbar,
              }}
              componentsProps={{
                toolbar: {
                  showQuickFilter: true,
                  quickFilterProps: {debounceMs: 500},
                  csvOptions: {
                    fileName: 'reportLocalExport',
                  },
                  printOptions: {
                    hideFooter: true,
                    hideToolbar: true,
                  },
                  exportOptions: () => ({
                    csv: {
                      fileName: 'reportLocalExport',
                    },
                    print: {
                      hideFooter: true,
                      hideToolbar: true,
                    },
                  }),
                },
              }}
          />
        </div>
      </div>
  );
}
