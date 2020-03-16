<template>
    <v-container grid-list-xl>
            <v-card-title>
                Sublime API's
                <v-spacer></v-spacer>
                <v-text-field v-model="search" append-icon="mdi-magnify" label="Search" single-line hide-details></v-text-field>
            </v-card-title>
            <v-data-table :headers="headers" :items="endpoints" :search="search"></v-data-table>
    </v-container>
</template>
<script>
import axios from 'axios'

export default {
    data() {
        return {
            search: '',
            headers: [{
                    text: 'Sublime Build',
                    align: 'start',
                    sortable: true,
                    value: 'version',
                },
                { text: 'API Endpoint', value: 'endpoint' },
            ],
            endpoints: [],
        }
    },
    mounted() {
        axios.get('https://raw.githubusercontent.com/TheSecEng/Sublime-Text-API-Tracker/master/sublime_api_list.json').then(res => {
            var sublime_data = { data: [], count: 0 };
            Object.keys(res.data).forEach(itemKey => {
                var sublime_version = itemKey;
                res.data[sublime_version].forEach(function(entry) {
                    var api_entry = { version: sublime_version, endpoint: entry };
                    sublime_data.data.push(api_entry);
                    sublime_data.count = sublime_data.count + 1;
                });
            });
            this.endpoints = sublime_data.data;
        })
    }
}
</script>