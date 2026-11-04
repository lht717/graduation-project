<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";

const props = defineProps({
  route: { type: String, required: true }
});

const router = useRouter();
const href = computed(() => `#${props.route}`);

function go(event) {
  event.preventDefault();
  router.push(`/${props.route}`);
}
</script>

<template>
  <a :href="href" :data-route="route" @click="go"><slot /></a>
</template>
