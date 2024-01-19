import * as React from 'react';
import {DataGrid, GridToolbar} from '@mui/x-data-grid';
import DateRangePickerComp from "../components/DatePickerComp";
import {useState} from "react";
import Wrapper from '../assets/wrappers/ChartsContainer';
import {useSelector} from "react-redux";
import customFetch, {checkForUnauthorizedResponse} from "../util/axios";
import {toast} from "react-toastify";

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