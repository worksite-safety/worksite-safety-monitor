import * as React from 'react';
import {DataGrid, GridToolbar} from '@mui/x-data-grid';
import DateRangePickerComp from "../components/DatePickerComp";
import {useState} from "react";
import Wrapper from '../assets/wrappers/ChartsContainer';
import {useSelector} from "react-redux";
import customFetch, {checkForUnauthorizedResponse} from "../util/axios";
import {toast} from "react-toastify";
import { DataGrid, GridToolbar, GridToolbarFilterButton } from '@mui/x-data-grid';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import customFetch from "../util/axios";


const VISIBLE_FIELDS = ['eventType', 'startTime', 'timePeriod', 'cameraName'];

export default function ControlledSort() {
  const [rows, setRows] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [sortModel, setSortModel] = React.useState([
    {
      field: 'startTime',
      sort: 'desc',
    },
  ]);
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
    const handleDeleteRow = async (id) => {
        try {
            // Assuming there is a unique identifier named 'id' for each row
            const response = await customFetch.delete(`event/delete-events/${id}`);

            if (response.status === 200) {
                // If the API call is successful, update the state to remove the deleted row
                const updatedRows = rows.filter((row) => row.id !== id);
                setRows(updatedRows);
            } else {
                // Handle error if the API call is not successful
                console.error('Failed to delete the row:', response.statusText);
            }
        } catch (error) {
            // Handle any network or unexpected errors
            console.error('Error while deleting the row:', error.message);
        }
    };



  React.useEffect(() => {
    const fetchCountableEventsData = async (startDate, endDate) => {
      setLoading(true);
      try {
        const response = await fetch(`http://localhost:8080/event/all-events`);
        const jsonData = await response.json();

        // Convert epoch time to human-readable format and handle zero timePeriod
        const modifiedRows = jsonData.map((row) => ({
          ...row,
          startTime: new Date(row.startTime).toLocaleString(),
          timePeriod: row.timePeriod === 0 ? '-' : row.timePeriod,
        }));

        setRows(modifiedRows);
      } catch (error) {
        // Handle error
      } finally {
        setLoading(false);
      }
    };

    const today = new Date();
    const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

    oneWeekAgo.setHours(0, 0, 1);
    today.setHours(23, 59, 59);

    fetchCountableEventsData(oneWeekAgo.getTime(), today.getTime());
  }, []); // Empty dependency array means this effect runs only once, when the component mounts

  const columns = VISIBLE_FIELDS.map(
      (field) => ({field, headerName: field, flex: 1}));
  const fetchEventsData = async (startDate, endDate) => {
    setLoading(true);
    try {
      const response = await customFetch.post(
          `/event/sendPdfEmail/${startDate}/${endDate}/${user.email}`
      );
      const jsonData = response.data;
      toast.success("Report sent successfully!");
      setEvents(jsonData);
    } catch (error) {
      console.error("Error fetching data:", error);
    const columns = [
        ...VISIBLE_FIELDS.map((field) => ({ field, headerName: field, flex: 1 })),
        {
            field: 'actions',
            headerName: 'Actions',
            flex: 1,
            sortable: false,
            renderCell: (params) => (
                <DeleteOutlineIcon
                    style={{ cursor: 'pointer' }}
                    onClick={() => handleDeleteRow(params.row.id)}
                />
            ),
        },
    ];


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
  return (
      <div>
        <Wrapper style={{display: "flex", justifyContent: "flex-end"}}>

          <DateRangePickerComp onApply={fetchEventsData} applyButtonLabel={"Send Report"} clearButtonLabel={"Clear"}/>
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
